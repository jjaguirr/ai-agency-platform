/**
 * SendGrid Email Service - Direct SDK Integration
 * Replaces missing @sendgrid/mcp-server package
 */
import sgMail from '@sendgrid/mail';

export class EmailService {
  constructor() {
    if (!process.env.SENDGRID_API_KEY) {
      throw new Error('SENDGRID_API_KEY environment variable is required');
    }
    sgMail.setApiKey(process.env.SENDGRID_API_KEY);
  }

  /**
   * Send transactional email
   */
  async sendEmail(params: {
    to: string | string[];
    subject: string;
    html: string;
    text?: string;
    from?: string;
    templateId?: string;
    dynamicTemplateData?: Record<string, any>;
  }) {
    const { to, subject, html, text, from, templateId, dynamicTemplateData } = params;
    
    const msg: any = {
      to,
      from: from || process.env.SENDGRID_FROM_EMAIL || 'noreply@aiagencyplatform.com',
      subject,
    };

    if (templateId) {
      msg.templateId = templateId;
      msg.dynamicTemplateData = dynamicTemplateData || {};
    } else {
      msg.html = html;
      msg.text = text || html.replace(/<[^>]*>/g, ''); // Strip HTML for text fallback
    }

    try {
      const result = await sgMail.send(msg);
      return {
        success: true,
        messageId: result[0].headers['x-message-id'],
        statusCode: result[0].statusCode
      };
    } catch (error: any) {
      console.error('SendGrid email error:', error);
      throw new Error(`Email send failed: ${error.message}`);
    }
  }

  /**
   * Send bulk emails with personalization
   */
  async sendBulkEmail(emails: Array<{
    to: string;
    subject: string;
    html: string;
    dynamicTemplateData?: Record<string, any>;
  }>) {
    const messages = emails.map(email => ({
      to: email.to,
      from: process.env.SENDGRID_FROM_EMAIL || 'noreply@aiagencyplatform.com',
      subject: email.subject,
      html: email.html,
      dynamicTemplateData: email.dynamicTemplateData
    }));

    try {
      const result = await sgMail.send(messages);
      return {
        success: true,
        sent: result.length,
        results: result.map(r => ({
          messageId: r.headers['x-message-id'],
          statusCode: r.statusCode
        }))
      };
    } catch (error: any) {
      console.error('SendGrid bulk email error:', error);
      throw new Error(`Bulk email send failed: ${error.message}`);
    }
  }

  /**
   * Validate email template
   */
  async validateTemplate(templateId: string, testData: Record<string, any>) {
    try {
      await sgMail.send({
        to: 'test@example.com',
        from: process.env.SENDGRID_FROM_EMAIL || 'noreply@aiagencyplatform.com',
        templateId,
        dynamicTemplateData: testData,
        mailSettings: {
          sandboxMode: { enable: true }
        }
      });
      return { valid: true };
    } catch (error: any) {
      return { valid: false, error: error.message };
    }
  }

  /**
   * Get email statistics
   */
  async getEmailStats(startDate: string, endDate: string) {
    // Note: This requires SendGrid's Web API v3, not just the mail library
    // Implementation would need @sendgrid/client for stats API
    console.warn('Email stats require @sendgrid/client - implement if needed');
    return { 
      delivered: 0, 
      opens: 0, 
      clicks: 0, 
      bounces: 0,
      note: 'Stats API not implemented - add @sendgrid/client if needed'
    };
  }
}

// Singleton instance
export const emailService = new EmailService();