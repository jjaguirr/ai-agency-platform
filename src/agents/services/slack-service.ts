/**
 * Slack Team Coordination Service - Direct SDK Integration
 * Replaces missing @slack/mcp-server package
 */
import { WebClient, ErrorCode, ChatPostMessageResponse } from '@slack/web-api';
import { EventEmitter } from 'events';

export interface SlackMessage {
  channel: string;
  text: string;
  blocks?: any[];
  attachments?: any[];
  threadTs?: string;
  username?: string;
  iconEmoji?: string;
}

export interface SlackChannel {
  id: string;
  name: string;
  purpose?: string;
  topic?: string;
  isPrivate: boolean;
  members?: string[];
}

export class SlackService extends EventEmitter {
  private client: WebClient;
  private botToken: string;
  private appToken?: string;

  constructor() {
    super();
    
    this.botToken = process.env.SLACK_BOT_TOKEN || '';
    this.appToken = process.env.SLACK_APP_TOKEN || '';
    
    if (!this.botToken) {
      throw new Error('SLACK_BOT_TOKEN environment variable is required');
    }
    
    this.client = new WebClient(this.botToken);
    this.validateConnection();
  }

  /**
   * Validate Slack API connection
   */
  private async validateConnection() {
    try {
      const auth = await this.client.auth.test();
      console.log(`Slack client connected as: ${auth.user} (${auth.team})`);
      this.emit('connected', { user: auth.user, team: auth.team });
    } catch (error: any) {
      console.error('Slack connection validation failed:', error);
      throw new Error(`Slack authentication failed: ${error.message}`);
    }
  }

  /**
   * Send message to a channel or user
   */
  async sendMessage(params: SlackMessage): Promise<ChatPostMessageResponse> {
    try {
      const result = await this.client.chat.postMessage({
        channel: params.channel,
        text: params.text,
        blocks: params.blocks,
        attachments: params.attachments,
        thread_ts: params.threadTs,
        username: params.username,
        icon_emoji: params.iconEmoji
      });
      
      this.emit('message:sent', {
        channel: params.channel,
        messageId: result.ts,
        success: result.ok
      });
      
      return result;
    } catch (error: any) {
      console.error('Slack message send error:', error);
      
      if (error.code === ErrorCode.ChannelNotFound) {
        throw new Error(`Channel not found: ${params.channel}`);
      } else if (error.code === ErrorCode.NotInChannel) {
        throw new Error(`Bot not in channel: ${params.channel}`);
      }
      
      throw new Error(`Message send failed: ${error.message}`);
    }
  }

  /**
   * Send rich message with blocks
   */
  async sendRichMessage(channel: string, blocks: any[], text?: string) {
    return this.sendMessage({
      channel,
      text: text || 'Rich message',
      blocks
    });
  }

  /**
   * Send notification with priority styling
   */
  async sendNotification(channel: string, title: string, message: string, priority: 'info' | 'warning' | 'error' | 'success' = 'info') {
    const colors = {
      info: '#2196F3',
      warning: '#FF9800',
      error: '#F44336',
      success: '#4CAF50'
    };
    
    const emojis = {
      info: ':information_source:',
      warning: ':warning:',
      error: ':exclamation:',
      success: ':white_check_mark:'
    };
    
    const blocks = [
      {
        type: 'section',
        text: {
          type: 'mrkdwn',
          text: `${emojis[priority]} *${title}*\n${message}`
        }
      }
    ];
    
    return this.sendMessage({
      channel,
      text: `${title}: ${message}`,
      blocks,
      attachments: [{
        color: colors[priority],
        fallback: `${title}: ${message}`
      }]
    });
  }

  /**
   * Create a new channel
   */
  async createChannel(name: string, purpose?: string, isPrivate: boolean = false): Promise<SlackChannel> {
    try {
      const result = await this.client.conversations.create({
        name: name.toLowerCase().replace(/[^a-z0-9-_]/g, ''),
        is_private: isPrivate
      });
      
      if (!result.channel) {
        throw new Error('Channel creation failed - no channel returned');
      }
      
      // Set channel purpose if provided
      if (purpose) {
        await this.client.conversations.setPurpose({
          channel: result.channel.id!,
          purpose
        });
      }
      
      const channelInfo: SlackChannel = {
        id: result.channel.id!,
        name: result.channel.name!,
        purpose,
        isPrivate: result.channel.is_private || false
      };
      
      this.emit('channel:created', channelInfo);
      
      return channelInfo;
    } catch (error: any) {
      console.error('Channel creation error:', error);
      
      if (error.code === ErrorCode.NameTaken) {
        throw new Error(`Channel name already taken: ${name}`);
      }
      
      throw new Error(`Channel creation failed: ${error.message}`);
    }
  }

  /**
   * Invite users to a channel
   */
  async inviteToChannel(channelId: string, userIds: string[]) {
    try {
      const result = await this.client.conversations.invite({
        channel: channelId,
        users: userIds.join(',')
      });
      
      this.emit('users:invited', { channelId, userIds, success: result.ok });
      
      return {
        channelId,
        invitedUsers: userIds,
        success: result.ok
      };
    } catch (error: any) {
      console.error('Channel invitation error:', error);
      throw new Error(`Failed to invite users to channel: ${error.message}`);
    }
  }

  /**
   * Get channel information
   */
  async getChannelInfo(channelId: string): Promise<SlackChannel> {
    try {
      const result = await this.client.conversations.info({
        channel: channelId
      });
      
      if (!result.channel) {
        throw new Error('Channel not found');
      }
      
      return {
        id: result.channel.id!,
        name: result.channel.name!,
        purpose: result.channel.purpose?.value,
        topic: result.channel.topic?.value,
        isPrivate: result.channel.is_private || false
      };
    } catch (error: any) {
      console.error('Channel info error:', error);
      throw new Error(`Failed to get channel info: ${error.message}`);
    }
  }

  /**
   * List all channels the bot has access to
   */
  async listChannels(includePrivate: boolean = false) {
    try {
      const result = await this.client.conversations.list({
        types: includePrivate ? 'public_channel,private_channel' : 'public_channel',
        limit: 1000
      });
      
      return result.channels?.map(channel => ({
        id: channel.id!,
        name: channel.name!,
        purpose: channel.purpose?.value,
        topic: channel.topic?.value,
        isPrivate: channel.is_private || false,
        memberCount: channel.num_members
      })) || [];
    } catch (error: any) {
      console.error('Channel listing error:', error);
      throw new Error(`Failed to list channels: ${error.message}`);
    }
  }

  /**
   * Get channel members
   */
  async getChannelMembers(channelId: string) {
    try {
      const result = await this.client.conversations.members({
        channel: channelId,
        limit: 1000
      });
      
      return result.members || [];
    } catch (error: any) {
      console.error('Channel members error:', error);
      throw new Error(`Failed to get channel members: ${error.message}`);
    }
  }

  /**
   * Schedule a message for later delivery
   */
  async scheduleMessage(channel: string, text: string, postAt: Date) {
    try {
      const postAtUnix = Math.floor(postAt.getTime() / 1000);
      
      const result = await this.client.chat.scheduleMessage({
        channel,
        text,
        post_at: postAtUnix
      });
      
      this.emit('message:scheduled', {
        channel,
        scheduledMessageId: result.scheduled_message_id,
        postAt
      });
      
      return {
        scheduledMessageId: result.scheduled_message_id,
        postAt,
        success: result.ok
      };
    } catch (error: any) {
      console.error('Message scheduling error:', error);
      throw new Error(`Message scheduling failed: ${error.message}`);
    }
  }

  /**
   * Upload file to channel
   */
  async uploadFile(channel: string, filePath: string, title?: string, comment?: string) {
    try {
      const result = await this.client.files.upload({
        channels: channel,
        file: require('fs').createReadStream(filePath),
        title,
        initial_comment: comment
      });
      
      this.emit('file:uploaded', {
        channel,
        fileId: result.file?.id,
        fileName: result.file?.name
      });
      
      return {
        fileId: result.file?.id,
        fileName: result.file?.name,
        url: result.file?.url_private,
        success: result.ok
      };
    } catch (error: any) {
      console.error('File upload error:', error);
      throw new Error(`File upload failed: ${error.message}`);
    }
  }

  /**
   * Add reaction to a message
   */
  async addReaction(channel: string, timestamp: string, emoji: string) {
    try {
      const result = await this.client.reactions.add({
        channel,
        timestamp,
        name: emoji.replace(/:/g, '') // Remove colons from emoji name
      });
      
      return { success: result.ok };
    } catch (error: any) {
      console.error('Reaction add error:', error);
      throw new Error(`Failed to add reaction: ${error.message}`);
    }
  }

  /**
   * Get user information
   */
  async getUserInfo(userId: string) {
    try {
      const result = await this.client.users.info({
        user: userId
      });
      
      if (!result.user) {
        throw new Error('User not found');
      }
      
      return {
        id: result.user.id!,
        name: result.user.name!,
        realName: result.user.real_name,
        displayName: result.user.profile?.display_name,
        email: result.user.profile?.email,
        timezone: result.user.tz,
        isBot: result.user.is_bot || false
      };
    } catch (error: any) {
      console.error('User info error:', error);
      throw new Error(`Failed to get user info: ${error.message}`);
    }
  }

  /**
   * Create agent coordination channel for a customer
   */
  async createAgentCoordinationChannel(customerId: string, agentTypes: string[]) {
    const channelName = `agent-coord-${customerId}`;
    const purpose = `Coordination channel for ${agentTypes.join(', ')} agents serving customer ${customerId}`;
    
    try {
      const channel = await this.createChannel(channelName, purpose, true);
      
      // Send welcome message
      await this.sendNotification(
        channel.id,
        'Agent Coordination Channel Created',
        `This channel coordinates ${agentTypes.length} agents for customer ${customerId}:\n• ${agentTypes.join('\n• ')}`,
        'info'
      );
      
      return channel;
    } catch (error: any) {
      // If channel exists, try to get existing channel
      if (error.message.includes('already taken')) {
        const channels = await this.listChannels(true);
        const existingChannel = channels.find(ch => ch.name === channelName);
        if (existingChannel) {
          return existingChannel;
        }
      }
      throw error;
    }
  }
}

// Singleton instance
export const slackService = new SlackService();