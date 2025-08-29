/**
 * AI Agency Platform - Core Authentication API
 * Phase 1: JWT-based authentication with complete customer isolation
 * Version: 1.0 - Foundation Infrastructure
 */

const jwt = require('jsonwebtoken');
const bcrypt = require('bcryptjs');
const { Pool } = require('pg');
const crypto = require('crypto');
const rateLimit = require('express-rate-limit');

// Database connection with customer isolation
const pool = new Pool({
    connectionString: process.env.PLATFORM_DATABASE_URL || 'postgresql://mcphub:mcphub_password@localhost:5432/mcphub',
    ssl: false,
    max: 20,
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 2000,
});

/**
 * JWT Configuration
 */
const JWT_CONFIG = {
    secret: process.env.JWT_SECRET || 'ai_agency_platform_jwt_secret_change_in_production',
    accessTokenExpiry: '15m',
    refreshTokenExpiry: '7d',
    algorithm: 'HS256'
};

/**
 * Rate limiting for authentication endpoints
 */
const authRateLimit = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    max: 5, // 5 attempts per window
    message: { error: 'Too many authentication attempts, please try again later' },
    standardHeaders: true,
    legacyHeaders: false,
});

const registerRateLimit = rateLimit({
    windowMs: 60 * 60 * 1000, // 1 hour
    max: 3, // 3 registrations per hour
    message: { error: 'Too many registration attempts, please try again later' },
    standardHeaders: true,
    legacyHeaders: false,
});

/**
 * Password hashing utilities
 */
const hashPassword = async (password) => {
    const saltRounds = 12;
    return await bcrypt.hash(password, saltRounds);
};

const verifyPassword = async (password, hashedPassword) => {
    return await bcrypt.compare(password, hashedPassword);
};

/**
 * JWT token utilities
 */
const generateTokens = (userId, customerId, email, role) => {
    const payload = {
        userId,
        customerId,
        email,
        role,
        type: 'access'
    };

    const accessToken = jwt.sign(payload, JWT_CONFIG.secret, {
        expiresIn: JWT_CONFIG.accessTokenExpiry,
        algorithm: JWT_CONFIG.algorithm
    });

    const refreshPayload = {
        userId,
        customerId,
        type: 'refresh'
    };

    const refreshToken = jwt.sign(refreshPayload, JWT_CONFIG.secret, {
        expiresIn: JWT_CONFIG.refreshTokenExpiry,
        algorithm: JWT_CONFIG.algorithm
    });

    return { accessToken, refreshToken };
};

const verifyToken = (token) => {
    try {
        return jwt.verify(token, JWT_CONFIG.secret);
    } catch (error) {
        throw new Error('Invalid token');
    }
};

/**
 * Database operations with customer isolation
 */
const createCustomer = async (businessName, businessType, contactEmail, contactPhone) => {
    const client = await pool.connect();
    
    try {
        await client.query('BEGIN');
        
        // Create customer
        const customerResult = await client.query(
            `INSERT INTO customers (business_name, business_type, contact_email, contact_phone, onboarding_status)
             VALUES ($1, $2, $3, $4, 'stage1')
             RETURNING id, business_name, contact_email, onboarding_status, created_at`,
            [businessName, businessType, contactEmail, contactPhone]
        );
        
        const customer = customerResult.rows[0];
        
        // Create default Tier 3 security group for customer
        await client.query(
            `INSERT INTO customer_security_groups (customer_id, group_tier, group_name, permissions)
             VALUES ($1, 3, $2, $3)`,
            [
                customer.id,
                `customer-${customer.id}`,
                JSON.stringify({
                    ai_models: ['gpt-4o', 'claude-3.5-sonnet'],
                    messaging_channels: ['whatsapp', 'email', 'instagram'],
                    workflow_creation: true,
                    agent_deployment: true
                })
            ]
        );
        
        await client.query('COMMIT');
        return customer;
        
    } catch (error) {
        await client.query('ROLLBACK');
        throw error;
    } finally {
        client.release();
    }
};

const createUser = async (customerId, email, password, fullName, role = 'user') => {
    const client = await pool.connect();
    
    try {
        await client.query('BEGIN');
        
        // Hash password
        const passwordHash = await hashPassword(password);
        
        // Create user with customer isolation
        const userResult = await client.query(
            `INSERT INTO users (customer_id, email, password_hash, full_name, role)
             VALUES ($1, $2, $3, $4, $5)
             RETURNING id, email, full_name, role, created_at`,
            [customerId, email, passwordHash, fullName, role]
        );
        
        const user = userResult.rows[0];
        
        // Log activity
        await client.query(
            `INSERT INTO customer_activities (customer_id, activity_type, activity_data, user_id)
             VALUES ($1, 'user_created', $2, $3)`,
            [customerId, JSON.stringify({ email, role }), user.id]
        );
        
        await client.query('COMMIT');
        return user;
        
    } catch (error) {
        await client.query('ROLLBACK');
        if (error.code === '23505') { // Unique violation
            throw new Error('Email already exists for this customer');
        }
        throw error;
    } finally {
        client.release();
    }
};

const authenticateUser = async (email, password, customerDomain = null) => {
    const client = await pool.connect();
    
    try {
        // Query user with customer context
        let query = `
            SELECT u.id, u.customer_id, u.email, u.password_hash, u.full_name, u.role, u.is_active,
                   c.business_name, c.subscription_tier, c.onboarding_status, c.is_active as customer_active
            FROM users u
            JOIN customers c ON u.customer_id = c.id
            WHERE u.email = $1 AND u.is_active = true AND c.is_active = true
        `;
        
        const params = [email];
        
        // Add customer domain filtering if provided
        if (customerDomain) {
            query += ' AND c.business_name ILIKE $2';
            params.push(`%${customerDomain}%`);
        }
        
        const result = await client.query(query, params);
        
        if (result.rows.length === 0) {
            throw new Error('Invalid credentials');
        }
        
        const user = result.rows[0];
        
        // Verify password
        const isValidPassword = await verifyPassword(password, user.password_hash);
        if (!isValidPassword) {
            // Log failed authentication attempt
            await client.query(
                `INSERT INTO audit_logs (customer_id, user_id, action, success, error_message)
                 VALUES ($1, $2, 'authentication_failed', false, 'Invalid password')`,
                [user.customer_id, user.id]
            );
            throw new Error('Invalid credentials');
        }
        
        // Update last login and log successful authentication
        await client.query(
            'UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = $1',
            [user.id]
        );
        
        await client.query(
            `INSERT INTO audit_logs (customer_id, user_id, action, success)
             VALUES ($1, $2, 'authentication_success', true)`,
            [user.customer_id, user.id]
        );
        
        await client.query(
            `INSERT INTO customer_activities (customer_id, activity_type, activity_data, user_id)
             VALUES ($1, 'user_login', $2, $3)`,
            [user.customer_id, JSON.stringify({ ip: 'unknown' }), user.id]
        );
        
        // Return user data without password hash
        const { password_hash, ...userWithoutPassword } = user;
        return userWithoutPassword;
        
    } finally {
        client.release();
    }
};

const storeRefreshToken = async (userId, customerId, tokenHash) => {
    const client = await pool.connect();
    
    try {
        await client.query(
            `INSERT INTO refresh_tokens (user_id, customer_id, token_hash, expires_at)
             VALUES ($1, $2, $3, CURRENT_TIMESTAMP + INTERVAL '7 days')`,
            [userId, customerId, tokenHash]
        );
    } finally {
        client.release();
    }
};

const verifyRefreshToken = async (tokenHash) => {
    const client = await pool.connect();
    
    try {
        const result = await client.query(
            `SELECT rt.user_id, rt.customer_id, u.email, u.role, u.is_active
             FROM refresh_tokens rt
             JOIN users u ON rt.user_id = u.id
             WHERE rt.token_hash = $1 
               AND rt.expires_at > CURRENT_TIMESTAMP 
               AND rt.is_revoked = false
               AND u.is_active = true`,
            [tokenHash]
        );
        
        return result.rows[0] || null;
        
    } finally {
        client.release();
    }
};

const revokeRefreshToken = async (tokenHash) => {
    const client = await pool.connect();
    
    try {
        await client.query(
            'UPDATE refresh_tokens SET is_revoked = true WHERE token_hash = $1',
            [tokenHash]
        );
    } finally {
        client.release();
    }
};

/**
 * API endpoints
 */

// Customer and user registration (LAUNCH Bot Stage 1)
const register = async (req, res) => {
    try {
        const { businessName, businessType, contactEmail, contactPhone, userFullName, userPassword } = req.body;
        
        // Validate required fields
        if (!businessName || !contactEmail || !userFullName || !userPassword) {
            return res.status(400).json({
                error: 'Missing required fields',
                required: ['businessName', 'contactEmail', 'userFullName', 'userPassword']
            });
        }
        
        // Validate email format
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(contactEmail)) {
            return res.status(400).json({ error: 'Invalid email format' });
        }
        
        // Validate password strength
        if (userPassword.length < 8) {
            return res.status(400).json({ error: 'Password must be at least 8 characters long' });
        }
        
        // Create customer and primary user
        const customer = await createCustomer(businessName, businessType, contactEmail, contactPhone);
        const user = await createUser(customer.id, contactEmail, userPassword, userFullName, 'admin');
        
        // Generate tokens
        const { accessToken, refreshToken } = generateTokens(
            user.id, 
            customer.id, 
            user.email, 
            user.role
        );
        
        // Store refresh token
        const refreshTokenHash = crypto.createHash('sha256').update(refreshToken).digest('hex');
        await storeRefreshToken(user.id, customer.id, refreshTokenHash);
        
        res.status(201).json({
            message: 'Registration successful',
            customer: {
                id: customer.id,
                businessName: customer.business_name,
                onboardingStatus: customer.onboarding_status
            },
            user: {
                id: user.id,
                email: user.email,
                fullName: user.full_name,
                role: user.role
            },
            tokens: {
                accessToken,
                refreshToken
            }
        });
        
    } catch (error) {
        console.error('Registration error:', error);
        
        if (error.message.includes('already exists')) {
            return res.status(409).json({ error: error.message });
        }
        
        res.status(500).json({ error: 'Registration failed' });
    }
};

// User authentication
const login = async (req, res) => {
    try {
        const { email, password, customerDomain } = req.body;
        
        if (!email || !password) {
            return res.status(400).json({ error: 'Email and password are required' });
        }
        
        // Authenticate user
        const user = await authenticateUser(email, password, customerDomain);
        
        // Generate tokens
        const { accessToken, refreshToken } = generateTokens(
            user.id, 
            user.customer_id, 
            user.email, 
            user.role
        );
        
        // Store refresh token
        const refreshTokenHash = crypto.createHash('sha256').update(refreshToken).digest('hex');
        await storeRefreshToken(user.id, user.customer_id, refreshTokenHash);
        
        res.json({
            message: 'Authentication successful',
            user: {
                id: user.id,
                email: user.email,
                fullName: user.full_name,
                role: user.role,
                customerId: user.customer_id,
                businessName: user.business_name,
                subscriptionTier: user.subscription_tier
            },
            tokens: {
                accessToken,
                refreshToken
            }
        });
        
    } catch (error) {
        console.error('Login error:', error);
        res.status(401).json({ error: 'Invalid credentials' });
    }
};

// Token refresh
const refreshAccessToken = async (req, res) => {
    try {
        const { refreshToken } = req.body;
        
        if (!refreshToken) {
            return res.status(400).json({ error: 'Refresh token is required' });
        }
        
        // Verify refresh token format
        const decoded = verifyToken(refreshToken);
        if (decoded.type !== 'refresh') {
            return res.status(401).json({ error: 'Invalid token type' });
        }
        
        // Check token in database
        const tokenHash = crypto.createHash('sha256').update(refreshToken).digest('hex');
        const user = await verifyRefreshToken(tokenHash);
        
        if (!user) {
            return res.status(401).json({ error: 'Invalid or expired refresh token' });
        }
        
        // Generate new access token
        const { accessToken } = generateTokens(
            user.user_id,
            user.customer_id,
            user.email,
            user.role
        );
        
        res.json({
            accessToken,
            message: 'Token refreshed successfully'
        });
        
    } catch (error) {
        console.error('Token refresh error:', error);
        res.status(401).json({ error: 'Invalid refresh token' });
    }
};

// Logout (revoke refresh token)
const logout = async (req, res) => {
    try {
        const { refreshToken } = req.body;
        
        if (refreshToken) {
            const tokenHash = crypto.createHash('sha256').update(refreshToken).digest('hex');
            await revokeRefreshToken(tokenHash);
        }
        
        res.json({ message: 'Logout successful' });
        
    } catch (error) {
        console.error('Logout error:', error);
        res.status(500).json({ error: 'Logout failed' });
    }
};

/**
 * Authentication middleware
 */
const authenticateToken = async (req, res, next) => {
    try {
        const authHeader = req.headers['authorization'];
        const token = authHeader && authHeader.split(' ')[1]; // Bearer TOKEN
        
        if (!token) {
            return res.status(401).json({ error: 'Access token required' });
        }
        
        const decoded = verifyToken(token);
        
        if (decoded.type !== 'access') {
            return res.status(401).json({ error: 'Invalid token type' });
        }
        
        // Add user context to request
        req.user = {
            userId: decoded.userId,
            customerId: decoded.customerId,
            email: decoded.email,
            role: decoded.role
        };
        
        // Set customer isolation context for database queries
        req.dbContext = {
            customerId: decoded.customerId
        };
        
        next();
        
    } catch (error) {
        console.error('Token verification error:', error);
        res.status(403).json({ error: 'Invalid or expired token' });
    }
};

// Role-based authorization middleware
const authorize = (allowedRoles = []) => {
    return (req, res, next) => {
        if (allowedRoles.length === 0) {
            return next(); // No role restrictions
        }
        
        if (!req.user || !allowedRoles.includes(req.user.role)) {
            return res.status(403).json({ error: 'Insufficient permissions' });
        }
        
        next();
    };
};

// Validate customer context middleware
const validateCustomerContext = async (req, res, next) => {
    try {
        const client = await pool.connect();
        
        try {
            // Verify customer is active and user has access
            const result = await client.query(
                `SELECT c.is_active, c.subscription_tier 
                 FROM customers c 
                 WHERE c.id = $1`,
                [req.user.customerId]
            );
            
            if (result.rows.length === 0 || !result.rows[0].is_active) {
                return res.status(403).json({ error: 'Customer account inactive' });
            }
            
            req.customer = result.rows[0];
            next();
            
        } finally {
            client.release();
        }
        
    } catch (error) {
        console.error('Customer validation error:', error);
        res.status(500).json({ error: 'Customer validation failed' });
    }
};

module.exports = {
    // Rate limiting
    authRateLimit,
    registerRateLimit,
    
    // Authentication endpoints
    register,
    login,
    refreshAccessToken,
    logout,
    
    // Middleware
    authenticateToken,
    authorize,
    validateCustomerContext,
    
    // Utilities (for testing and internal use)
    generateTokens,
    verifyToken,
    hashPassword,
    verifyPassword
};