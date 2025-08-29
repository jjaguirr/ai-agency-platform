/**
 * Docker Orchestration Service - Direct SDK Integration
 * Replaces missing @docker/mcp-server package
 */
import Docker from 'dockerode';
import { EventEmitter } from 'events';

export interface ContainerConfig {
  image: string;
  name?: string;
  env?: string[];
  ports?: Record<string, {}>;
  volumes?: string[];
  restart?: 'no' | 'always' | 'unless-stopped' | 'on-failure';
  labels?: Record<string, string>;
  networkMode?: string;
  memory?: number;
  cpus?: number;
}

export interface ServiceScaleConfig {
  serviceName: string;
  replicas: number;
  updateConfig?: {
    parallelism: number;
    delay: string;
  };
}

export class DockerService extends EventEmitter {
  private docker: Docker;

  constructor() {
    super();
    
    const socketPath = process.env.DOCKER_SOCKET_PATH || '/var/run/docker.sock';
    
    // Initialize Docker connection
    this.docker = new Docker({
      socketPath,
      timeout: 60000
    });
    
    this.validateConnection();
  }

  /**
   * Validate Docker daemon connection
   */
  private async validateConnection() {
    try {
      await this.docker.ping();
      console.log('Docker daemon connection established');
    } catch (error) {
      console.error('Docker daemon connection failed:', error);
      throw new Error(`Docker connection failed. Ensure Docker is running and socket is accessible: ${error}`);
    }
  }

  /**
   * Deploy a new container
   */
  async deployContainer(config: ContainerConfig) {
    try {
      // Pull image if not exists
      await this.pullImage(config.image);
      
      // Create container
      const container = await this.docker.createContainer({
        Image: config.image,
        name: config.name,
        Env: config.env,
        ExposedPorts: config.ports,
        HostConfig: {
          PortBindings: config.ports,
          Binds: config.volumes,
          RestartPolicy: { Name: config.restart || 'unless-stopped' },
          Memory: config.memory,
          NanoCpus: config.cpus ? config.cpus * 1000000000 : undefined,
          NetworkMode: config.networkMode
        },
        Labels: {
          'ai-agency-platform': 'true',
          ...config.labels
        }
      });

      // Start container
      await container.start();
      
      const info = await container.inspect();
      
      this.emit('container:deployed', {
        id: info.Id,
        name: info.Name,
        status: info.State.Status,
        image: config.image
      });

      return {
        containerId: info.Id,
        name: info.Name,
        status: info.State.Status,
        ports: info.NetworkSettings.Ports,
        ipAddress: info.NetworkSettings.IPAddress
      };
    } catch (error: any) {
      console.error('Container deployment error:', error);
      throw new Error(`Container deployment failed: ${error.message}`);
    }
  }

  /**
   * Scale a Docker service (Swarm mode)
   */
  async scaleService(config: ServiceScaleConfig) {
    try {
      const service = this.docker.getService(config.serviceName);
      const serviceInfo = await service.inspect();
      
      // Update service with new replica count
      await service.update({
        version: serviceInfo.Version.Index,
        Name: config.serviceName,
        Mode: {
          Replicated: {
            Replicas: config.replicas
          }
        },
        UpdateConfig: config.updateConfig
      });

      this.emit('service:scaled', {
        serviceName: config.serviceName,
        replicas: config.replicas
      });

      return {
        serviceName: config.serviceName,
        previousReplicas: serviceInfo.Spec.Mode.Replicated?.Replicas || 0,
        newReplicas: config.replicas,
        scaled: true
      };
    } catch (error: any) {
      console.error('Service scaling error:', error);
      throw new Error(`Service scaling failed: ${error.message}`);
    }
  }

  /**
   * Pull Docker image
   */
  async pullImage(imageName: string) {
    try {
      console.log(`Pulling image: ${imageName}`);
      const stream = await this.docker.pull(imageName);
      
      return new Promise((resolve, reject) => {
        this.docker.modem.followProgress(stream, (err: any, res: any) => {
          if (err) {
            reject(new Error(`Image pull failed: ${err.message}`));
          } else {
            console.log(`Image pulled successfully: ${imageName}`);
            resolve(res);
          }
        });
      });
    } catch (error: any) {
      console.error('Image pull error:', error);
      throw new Error(`Failed to pull image ${imageName}: ${error.message}`);
    }
  }

  /**
   * List running containers
   */
  async listContainers(all: boolean = false) {
    try {
      const containers = await this.docker.listContainers({ all });
      return containers.map(container => ({
        id: container.Id,
        name: container.Names[0].replace('/', ''),
        image: container.Image,
        status: container.Status,
        state: container.State,
        ports: container.Ports,
        labels: container.Labels
      }));
    } catch (error: any) {
      console.error('Container listing error:', error);
      throw new Error(`Failed to list containers: ${error.message}`);
    }
  }

  /**
   * Get container logs
   */
  async getContainerLogs(containerId: string, tail: number = 100) {
    try {
      const container = this.docker.getContainer(containerId);
      const logs = await container.logs({
        stdout: true,
        stderr: true,
        tail,
        timestamps: true
      });
      
      return logs.toString('utf8');
    } catch (error: any) {
      console.error('Container logs error:', error);
      throw new Error(`Failed to get logs for ${containerId}: ${error.message}`);
    }
  }

  /**
   * Stop container
   */
  async stopContainer(containerId: string, timeout: number = 10) {
    try {
      const container = this.docker.getContainer(containerId);
      await container.stop({ t: timeout });
      
      this.emit('container:stopped', { containerId });
      
      return { containerId, stopped: true };
    } catch (error: any) {
      console.error('Container stop error:', error);
      throw new Error(`Failed to stop container ${containerId}: ${error.message}`);
    }
  }

  /**
   * Remove container
   */
  async removeContainer(containerId: string, force: boolean = false) {
    try {
      const container = this.docker.getContainer(containerId);
      await container.remove({ force });
      
      this.emit('container:removed', { containerId });
      
      return { containerId, removed: true };
    } catch (error: any) {
      console.error('Container remove error:', error);
      throw new Error(`Failed to remove container ${containerId}: ${error.message}`);
    }
  }

  /**
   * Restart container
   */
  async restartContainer(containerId: string, timeout: number = 10) {
    try {
      const container = this.docker.getContainer(containerId);
      await container.restart({ t: timeout });
      
      this.emit('container:restarted', { containerId });
      
      return { containerId, restarted: true };
    } catch (error: any) {
      console.error('Container restart error:', error);
      throw new Error(`Failed to restart container ${containerId}: ${error.message}`);
    }
  }

  /**
   * Get container resource usage stats
   */
  async getContainerStats(containerId: string) {
    try {
      const container = this.docker.getContainer(containerId);
      const stats = await container.stats({ stream: false });
      
      // Calculate CPU usage percentage
      const cpuDelta = stats.cpu_stats.cpu_usage.total_usage - stats.precpu_stats.cpu_usage.total_usage;
      const systemDelta = stats.cpu_stats.system_cpu_usage - stats.precpu_stats.system_cpu_usage;
      const cpuPercent = (cpuDelta / systemDelta) * stats.cpu_stats.online_cpus * 100;
      
      // Calculate memory usage
      const memoryUsage = stats.memory_stats.usage;
      const memoryLimit = stats.memory_stats.limit;
      const memoryPercent = (memoryUsage / memoryLimit) * 100;
      
      return {
        containerId,
        cpu: {
          usage: cpuPercent.toFixed(2),
          cores: stats.cpu_stats.online_cpus
        },
        memory: {
          usage: memoryUsage,
          limit: memoryLimit,
          percent: memoryPercent.toFixed(2)
        },
        network: stats.networks,
        timestamp: new Date().toISOString()
      };
    } catch (error: any) {
      console.error('Container stats error:', error);
      throw new Error(`Failed to get stats for ${containerId}: ${error.message}`);
    }
  }

  /**
   * Create Docker network
   */
  async createNetwork(name: string, driver: string = 'bridge') {
    try {
      const network = await this.docker.createNetwork({
        Name: name,
        Driver: driver,
        Labels: {
          'ai-agency-platform': 'true'
        }
      });
      
      return {
        networkId: network.id,
        name,
        driver,
        created: true
      };
    } catch (error: any) {
      console.error('Network creation error:', error);
      throw new Error(`Failed to create network ${name}: ${error.message}`);
    }
  }

  /**
   * Deploy multi-container application with docker-compose-like functionality
   */
  async deployStack(stackName: string, services: Record<string, ContainerConfig>) {
    const deployedServices: Record<string, any> = {};
    
    try {
      // Create network for the stack
      const networkName = `${stackName}-network`;
      await this.createNetwork(networkName);
      
      // Deploy each service
      for (const [serviceName, config] of Object.entries(services)) {
        const containerConfig = {
          ...config,
          name: `${stackName}-${serviceName}`,
          networkMode: networkName,
          labels: {
            ...config.labels,
            'stack.name': stackName,
            'service.name': serviceName
          }
        };
        
        deployedServices[serviceName] = await this.deployContainer(containerConfig);
      }
      
      this.emit('stack:deployed', { stackName, services: Object.keys(services) });
      
      return {
        stackName,
        network: networkName,
        services: deployedServices,
        deployed: true
      };
    } catch (error: any) {
      console.error('Stack deployment error:', error);
      throw new Error(`Stack deployment failed: ${error.message}`);
    }
  }
}

// Singleton instance
export const dockerService = new DockerService();