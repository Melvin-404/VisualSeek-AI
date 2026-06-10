/**
 * Shared Type Definitions.
 *
 * This file contains global TS interfaces and types shared across the monorepo.
 */

export interface GPUHealthReport {
  cudaAvailable: boolean;
  gpuName: string;
  driverVersion: string;
  cudaVersion: string;
  totalMemoryMb: number;
  computeCapability: string;
  status: "healthy" | "degraded" | "failed";
  timestamp: string;
}

export interface APIHealthResponse {
  status: "healthy" | "unhealthy";
  environment: string;
  gpu?: GPUHealthReport;
}
