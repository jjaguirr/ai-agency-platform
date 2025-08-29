/**
 * AI Agency Platform - Main API Server
 * Phase 1: Foundation infrastructure with customer isolation
 * Version: 1.0 - Core platform API
 */

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const compression = require('compression');
const rateLimit = require('express-rate-limit');
const { Pool } = require('pg');

// Import authentication system
const auth = require('./auth');

// Import API modules (will be created)
// const agents = require('./agents');
// const workflows = require('./workflows'); 
// const messaging = require('./messaging');

const app = express();

// ====================================================================
// SECURITY & MIDDLEWARE CONFIGURATION
// ====================================================================

// Security headers
app.use(helmet({
    contentSecurityPolicy: {
        directives: {
            defaultSrc: ["'self'"],
            styleSrc: ["'self'", "'unsafe-inline'"],
            scriptSrc: ["'self'"],
            imgSrc: ["'self'", "data:", "https:"],
            connectSrc: ["'self'", "ws:", "wss:"]
        }
    },
    hsts: {
        maxAge: 31536000,
        includeSubDomains: true,
        preload: true
    }
}));

// CORS configuration - restrictive for production
app.use(cors({
    origin: function (origin, callback) {
        // Allow requests with no origin (mobile apps, postman, etc.)
        if (!origin) return callback(null, true);
        
        const allowedOrigins = [
            'http://localhost:3000',
            'http://localhost:3001', 
            'http://localhost:8000',
            'https://ai-agency-platform.com' // Production domain
        ];
        
        if (allowedOrigins.includes(origin)) {
            callback(null, true);
        } else {
            callback(new Error('Not allowed by CORS'));
        }
    },
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'X-Customer-ID']
}));

// Request parsing
app.use(express.json({ 
    limit: '10mb',
    verify: (req, res, buf) => {
        // Basic request validation
        if (buf.length === 0) return;
        try {
            JSON.parse(buf);
        } catch (e) {
            throw new Error('Invalid JSON');
        }
    }
}));

app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Response compression
app.use(compression());

// Global rate limiting
const globalRateLimit = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    max: 1000, // 1000 requests per window
    message: { 
        error: 'Too many requests from this IP, please try again later',
        retryAfter: '15 minutes'
    },
    standardHeaders: true,
    legacyHeaders: false,
});

app.use(globalRateLimit);

// Request logging middleware
app.use((req, res, next) => {
    const start = Date.now();
    
    res.on('finish', () => {
        const duration = Date.now() - start;
        const logData = {
            timestamp: new Date().toISOString(),
            method: req.method,
            url: req.url,
            status: res.statusCode,
            duration,
            userAgent: req.get('User-Agent'),
            ip: req.ip || req.connection.remoteAddress,
            customerId: req.user?.customerId || null
        };
        
        // Log to console in development, could be extended to proper logging service
        if (process.env.NODE_ENV !== 'test') {
            console.log(`[${logData.timestamp}] ${logData.method} ${logData.url} - ${logData.status} - ${duration}ms`);
        }
    });
    
    next();
});

// Error handling for JSON parsing
app.use((error, req, res, next) => {
    if (error instanceof SyntaxError && error.status === 400 && 'body' in error) {
        return res.status(400).json({ error: 'Invalid JSON format' });
    }
    next(error);
});

// ====================================================================
// DATABASE CONNECTION
// ====================================================================

const pool = new Pool({
    connectionString: process.env.PLATFORM_DATABASE_URL || 'postgresql://mcphub:mcphub_password@localhost:5432/mcphub',
    ssl: false,
    max: 20,
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 2000,
});

// Database health check
const checkDatabaseHealth = async () => {
    try {
        const client = await pool.connect();
        await client.query('SELECT 1');
        client.release();
        return { status: 'healthy' };
    } catch (error) {
        return { status: 'unhealthy', error: error.message };
    }
};

// ====================================================================
// API ROUTES
// ====================================================================

// Health check endpoint
app.get('/health', async (req, res) => {
    const dbHealth = await checkDatabaseHealth();
    
    const healthStatus = {
        status: dbHealth.status === 'healthy' ? 'healthy' : 'degraded',
        timestamp: new Date().toISOString(),
        version: '1.0.0',
        environment: process.env.NODE_ENV || 'development',
        services: {
            database: dbHealth,
            mcphub: {
                status: 'checking',
                url: process.env.MCPHUB_URL || 'http://localhost:3000'
            }
        }
    };
    
    // Check MCPhub connectivity
    try {
        const mcphubResponse = await fetch(`${process.env.MCPHUB_URL}/health`, {
            headers: {
                'Authorization': `Bearer ${process.env.MCPHUB_AUTH_TOKEN}`
            },
            timeout: 5000
        });
        
        healthStatus.services.mcphub.status = mcphubResponse.ok ? 'healthy' : 'unhealthy';
    } catch (error) {
        healthStatus.services.mcphub.status = 'unhealthy';
        healthStatus.services.mcphub.error = error.message;
    }
    
    const httpStatus = healthStatus.status === 'healthy' ? 200 : 503;
    res.status(httpStatus).json(healthStatus);
});

// API information endpoint
app.get('/api', (req, res) => {
    res.json({
        name: 'AI Agency Platform API',
        version: '1.0.0',
        phase: 'Phase 1 - Foundation Infrastructure',
        documentation: '/api/docs',
        health: '/health',
        authentication: {
            register: 'POST /api/auth/register',
            login: 'POST /api/auth/login',
            refresh: 'POST /api/auth/refresh',
            logout: 'POST /api/auth/logout'
        },
        endpoints: {
            customers: '/api/customers',
            agents: '/api/agents',
            workflows: '/api/workflows',
            messaging: '/api/messaging'
        }
    });
});

// ====================================================================
// AUTHENTICATION ROUTES
// ====================================================================

const authRouter = express.Router();

// Registration endpoint (LAUNCH Bot Stage 1)
authRouter.post('/register', auth.registerRateLimit, auth.register);

// Login endpoint
authRouter.post('/login', auth.authRateLimit, auth.login);

// Token refresh endpoint
authRouter.post('/refresh', auth.refreshAccessToken);

// Logout endpoint
authRouter.post('/logout', auth.logout);

// User profile endpoint (protected)
authRouter.get('/profile', auth.authenticateToken, auth.validateCustomerContext, async (req, res) => {
    try {
        const client = await pool.connect();
        
        try {
            const result = await client.query(`
                SELECT u.id, u.email, u.full_name, u.role, u.last_login, u.created_at,
                       c.business_name, c.subscription_tier, c.onboarding_status
                FROM users u
                JOIN customers c ON u.customer_id = c.id
                WHERE u.id = $1 AND u.customer_id = $2
            `, [req.user.userId, req.user.customerId]);
            
            if (result.rows.length === 0) {
                return res.status(404).json({ error: 'User not found' });
            }
            
            const user = result.rows[0];
            res.json({
                user: {
                    id: user.id,
                    email: user.email,
                    fullName: user.full_name,
                    role: user.role,
                    lastLogin: user.last_login,
                    createdAt: user.created_at
                },
                customer: {
                    businessName: user.business_name,
                    subscriptionTier: user.subscription_tier,
                    onboardingStatus: user.onboarding_status
                }
            });
            
        } finally {
            client.release();
        }
        
    } catch (error) {
        console.error('Profile fetch error:', error);
        res.status(500).json({ error: 'Failed to fetch user profile' });
    }
});

app.use('/api/auth', authRouter);

// ====================================================================
// CUSTOMER MANAGEMENT ROUTES (Protected)
// ====================================================================

const customerRouter = express.Router();

// Apply authentication middleware to all customer routes
customerRouter.use(auth.authenticateToken);
customerRouter.use(auth.validateCustomerContext);

// Get customer information
customerRouter.get('/', async (req, res) => {
    try {
        const client = await pool.connect();
        
        try {
            const result = await client.query(`
                SELECT id, business_name, business_type, contact_email, contact_phone,
                       onboarding_status, subscription_tier, api_quota_limit, api_quota_used,
                       api_quota_reset_date, created_at, last_activity
                FROM customers
                WHERE id = $1 AND is_active = true
            `, [req.user.customerId]);
            
            if (result.rows.length === 0) {
                return res.status(404).json({ error: 'Customer not found' });
            }
            
            res.json({ customer: result.rows[0] });
            
        } finally {
            client.release();
        }
        
    } catch (error) {
        console.error('Customer fetch error:', error);
        res.status(500).json({ error: 'Failed to fetch customer information' });
    }
});

// Update customer information
customerRouter.patch('/', auth.authorize(['admin', 'manager']), async (req, res) => {
    try {
        const { businessName, businessType, contactPhone } = req.body;
        const client = await pool.connect();
        
        try {
            await client.query('BEGIN');
            
            const updateFields = [];
            const values = [];
            let valueIndex = 1;
            
            if (businessName !== undefined) {
                updateFields.push(`business_name = $${valueIndex}`);
                values.push(businessName);
                valueIndex++;
            }
            
            if (businessType !== undefined) {
                updateFields.push(`business_type = $${valueIndex}`);
                values.push(businessType);
                valueIndex++;
            }
            
            if (contactPhone !== undefined) {
                updateFields.push(`contact_phone = $${valueIndex}`);
                values.push(contactPhone);
                valueIndex++;
            }
            
            if (updateFields.length === 0) {
                return res.status(400).json({ error: 'No valid fields to update' });
            }
            
            updateFields.push(`updated_at = CURRENT_TIMESTAMP`);
            values.push(req.user.customerId);
            
            const query = `
                UPDATE customers 
                SET ${updateFields.join(', ')}
                WHERE id = $${valueIndex}
                RETURNING business_name, business_type, contact_phone, updated_at
            `;
            
            const result = await client.query(query, values);
            
            // Log the activity
            await client.query(`
                INSERT INTO customer_activities (customer_id, activity_type, activity_data, user_id)
                VALUES ($1, 'customer_updated', $2, $3)
            `, [req.user.customerId, JSON.stringify(req.body), req.user.userId]);
            
            await client.query('COMMIT');
            
            res.json({
                message: 'Customer information updated successfully',
                customer: result.rows[0]
            });
            
        } catch (error) {
            await client.query('ROLLBACK');
            throw error;
        } finally {
            client.release();
        }
        
    } catch (error) {
        console.error('Customer update error:', error);
        res.status(500).json({ error: 'Failed to update customer information' });
    }
});

app.use('/api/customers', customerRouter);

// ====================================================================
// PLACEHOLDER ROUTES (To be implemented)
// ====================================================================

// Agents API routes (Phase 1 - Core 4 agents)
app.use('/api/agents', auth.authenticateToken, auth.validateCustomerContext, (req, res) => {
    res.status(501).json({ 
        message: 'Agents API - Coming in next development iteration',
        phase: 'Phase 1',
        targetAgents: ['social_media_manager', 'finance_agent', 'marketing_agent', 'business_agent']
    });
});

// Workflows API routes (n8n integration)
app.use('/api/workflows', auth.authenticateToken, auth.validateCustomerContext, (req, res) => {
    res.status(501).json({ 
        message: 'Workflows API - Coming in next development iteration',
        phase: 'Phase 1',
        integration: 'n8n automation platform'
    });
});

// Messaging API routes (WhatsApp, Email, Instagram)
app.use('/api/messaging', auth.authenticateToken, auth.validateCustomerContext, (req, res) => {
    res.status(501).json({ 
        message: 'Messaging API - Coming in next development iteration', 
        phase: 'Phase 1',
        channels: ['whatsapp', 'email', 'instagram']
    });
});

// ====================================================================
// ERROR HANDLING
// ====================================================================

// 404 handler for API routes
app.use('/api/*', (req, res) => {
    res.status(404).json({ 
        error: 'API endpoint not found',
        method: req.method,
        path: req.originalUrl,
        availableEndpoints: ['/api/auth', '/api/customers', '/api/agents', '/api/workflows', '/api/messaging']
    });
});

// Global error handler
app.use((error, req, res, next) => {
    console.error('Unhandled error:', error);
    
    // Don't send error details in production
    const isDevelopment = process.env.NODE_ENV === 'development';
    
    res.status(500).json({
        error: 'Internal server error',
        message: isDevelopment ? error.message : 'Something went wrong',
        stack: isDevelopment ? error.stack : undefined
    });
});

// ====================================================================
// SERVER STARTUP
// ====================================================================

const PORT = process.env.PLATFORM_API_PORT || process.env.PORT || 8000;

const startServer = async () => {
    try {
        // Test database connection
        const dbHealth = await checkDatabaseHealth();
        if (dbHealth.status !== 'healthy') {
            console.error('Database connection failed:', dbHealth.error);
            process.exit(1);
        }
        
        console.log('✅ Database connection healthy');
        
        // Start HTTP server
        const server = app.listen(PORT, '0.0.0.0', () => {
            console.log(`🚀 AI Agency Platform API Server running on port ${PORT}`);
            console.log(`📊 Health check: http://localhost:${PORT}/health`);
            console.log(`📖 API info: http://localhost:${PORT}/api`);
            console.log(`🔐 Authentication: http://localhost:${PORT}/api/auth`);
            console.log(`🏢 Environment: ${process.env.NODE_ENV || 'development'}`);
            console.log(`🗄️  Database: Connected to PostgreSQL`);
            console.log(`🛡️  MCPhub integration: ${process.env.MCPHUB_URL || 'http://localhost:3000'}`);
        });
        
        // Graceful shutdown
        process.on('SIGTERM', () => {
            console.log('SIGTERM signal received: closing HTTP server');
            server.close(() => {
                console.log('HTTP server closed');
                pool.end(() => {
                    console.log('Database pool closed');
                    process.exit(0);
                });
            });
        });
        
        process.on('SIGINT', () => {
            console.log('SIGINT signal received: closing HTTP server');
            server.close(() => {
                console.log('HTTP server closed');
                pool.end(() => {
                    console.log('Database pool closed');
                    process.exit(0);
                });
            });
        });
        
        return server;
        
    } catch (error) {
        console.error('Failed to start server:', error);
        process.exit(1);
    }
};

// Start server if this file is run directly
if (require.main === module) {
    startServer();
}

module.exports = { app, startServer };