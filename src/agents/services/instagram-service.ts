/**
 * Instagram Graph API Service - Direct SDK Integration
 * Replaces missing @instagram/mcp-server package
 */
import axios, { AxiosInstance } from 'axios';

export class InstagramService {
  private client: AxiosInstance;
  private accessToken: string;
  private apiVersion: string = 'v20.0';

  constructor() {
    this.accessToken = process.env.INSTAGRAM_ACCESS_TOKEN || '';
    if (!this.accessToken) {
      throw new Error('INSTAGRAM_ACCESS_TOKEN environment variable is required');
    }

    this.client = axios.create({
      baseURL: `https://graph.instagram.com/${this.apiVersion}`,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      }
    });
  }

  /**
   * Get Instagram Business account info
   */
  async getAccountInfo(userId?: string) {
    try {
      const accountId = userId || 'me';
      const response = await this.client.get(`/${accountId}`, {
        params: {
          fields: 'id,username,name,profile_picture_url,followers_count,media_count,biography',
          access_token: this.accessToken
        }
      });
      return response.data;
    } catch (error: any) {
      console.error('Instagram account info error:', error);
      throw new Error(`Failed to get account info: ${error.response?.data?.error?.message || error.message}`);
    }
  }

  /**
   * Get user's media posts
   */
  async getUserMedia(userId: string, limit: number = 25) {
    try {
      const response = await this.client.get(`/${userId}/media`, {
        params: {
          fields: 'id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,like_count,comments_count',
          limit,
          access_token: this.accessToken
        }
      });
      return {
        data: response.data.data,
        paging: response.data.paging
      };
    } catch (error: any) {
      console.error('Instagram media fetch error:', error);
      throw new Error(`Failed to get media: ${error.response?.data?.error?.message || error.message}`);
    }
  }

  /**
   * Create media container (step 1 of publishing)
   */
  async createMediaContainer(params: {
    userId: string;
    imageUrl?: string;
    videoUrl?: string;
    caption?: string;
    locationId?: string;
    userTags?: Array<{ username: string; x: number; y: number }>;
  }) {
    const { userId, imageUrl, videoUrl, caption, locationId, userTags } = params;
    
    if (!imageUrl && !videoUrl) {
      throw new Error('Either imageUrl or videoUrl is required');
    }

    try {
      const mediaData: any = {
        access_token: this.accessToken,
        caption: caption || '',
      };

      if (imageUrl) {
        mediaData.image_url = imageUrl;
      } else if (videoUrl) {
        mediaData.video_url = videoUrl;
        mediaData.media_type = 'VIDEO';
      }

      if (locationId) {
        mediaData.location_id = locationId;
      }

      if (userTags && userTags.length > 0) {
        mediaData.user_tags = JSON.stringify(userTags);
      }

      const response = await this.client.post(`/${userId}/media`, mediaData);
      return {
        containerId: response.data.id,
        success: true
      };
    } catch (error: any) {
      console.error('Instagram media container error:', error);
      throw new Error(`Failed to create media container: ${error.response?.data?.error?.message || error.message}`);
    }
  }

  /**
   * Publish media container (step 2 of publishing)
   */
  async publishMedia(userId: string, containerId: string) {
    try {
      const response = await this.client.post(`/${userId}/media_publish`, {
        creation_id: containerId,
        access_token: this.accessToken
      });
      return {
        mediaId: response.data.id,
        published: true
      };
    } catch (error: any) {
      console.error('Instagram publish error:', error);
      throw new Error(`Failed to publish media: ${error.response?.data?.error?.message || error.message}`);
    }
  }

  /**
   * Complete workflow: Create and publish content
   */
  async publishPhoto(params: {
    userId: string;
    imageUrl: string;
    caption: string;
    locationId?: string;
    userTags?: Array<{ username: string; x: number; y: number }>;
  }) {
    try {
      // Step 1: Create container
      const container = await this.createMediaContainer(params);
      
      // Step 2: Publish
      const published = await this.publishMedia(params.userId, container.containerId);
      
      return {
        success: true,
        mediaId: published.mediaId,
        containerId: container.containerId
      };
    } catch (error: any) {
      console.error('Instagram publish workflow error:', error);
      throw new Error(`Publish workflow failed: ${error.message}`);
    }
  }

  /**
   * Get media insights/analytics
   */
  async getMediaInsights(mediaId: string) {
    try {
      const response = await this.client.get(`/${mediaId}/insights`, {
        params: {
          metric: 'impressions,reach,likes,comments,saves,shares',
          access_token: this.accessToken
        }
      });
      
      const insights: Record<string, number> = {};
      response.data.data.forEach((metric: any) => {
        insights[metric.name] = metric.values[0].value;
      });
      
      return insights;
    } catch (error: any) {
      console.error('Instagram insights error:', error);
      throw new Error(`Failed to get insights: ${error.response?.data?.error?.message || error.message}`);
    }
  }

  /**
   * Get hashtag information
   */
  async searchHashtag(hashtag: string) {
    try {
      const response = await this.client.get('/ig_hashtag_search', {
        params: {
          q: hashtag,
          access_token: this.accessToken
        }
      });
      return response.data.data[0] || null;
    } catch (error: any) {
      console.error('Instagram hashtag search error:', error);
      throw new Error(`Hashtag search failed: ${error.response?.data?.error?.message || error.message}`);
    }
  }

  /**
   * Validate access token
   */
  async validateToken() {
    try {
      const response = await this.client.get('/me', {
        params: {
          fields: 'id,username',
          access_token: this.accessToken
        }
      });
      return {
        valid: true,
        user: response.data
      };
    } catch (error: any) {
      return {
        valid: false,
        error: error.response?.data?.error?.message || error.message
      };
    }
  }
}

// Singleton instance
export const instagramService = new InstagramService();