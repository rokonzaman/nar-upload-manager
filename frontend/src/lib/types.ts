/** TypeScript types mirroring the backend API contract (API_CONTRACT.md). */

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface UserOut {
  id: number;
  username: string;
  email: string | null;
  full_name: string | null;
  role: "admin" | "developer" | "viewer";
  is_active: boolean;
  deploy_environments: string | null;
  created_at: string;
  last_login: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserOut;
}

export interface AuthConfig {
  dev_mode: boolean;
  keycloak_enabled: boolean;
  app_name: string;
  version: string;
}

export interface NiFiServerOut {
  id: number;
  name: string;
  hostname: string;
  ssh_host: string;
  ssh_port: number;
  ssh_user: string;
  ssh_key_path: string | null;
  has_ssh_password: boolean;
  nar_directory: string;
  backup_directory: string;
  nifi_install_directory: string;
  restart_command: string;
  nifi_api_url: string | null;
  environment: string;
  is_enabled: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface NiFiServerCreate {
  name: string;
  hostname: string;
  ssh_host: string;
  ssh_port: number;
  ssh_user: string;
  ssh_key_path?: string | null;
  ssh_password?: string | null;
  nar_directory: string;
  backup_directory: string;
  nifi_install_directory: string;
  restart_command: string;
  nifi_api_url?: string | null;
  environment: string;
  is_enabled: boolean;
  description?: string | null;
}

export interface ServerTestResult {
  success: boolean;
  message: string;
  latency_ms: number | null;
  nifi_version: string | null;
}

export interface ServerGroupOut {
  id: number;
  name: string;
  description: string | null;
  environment: string;
  created_at: string;
  servers: NiFiServerOut[];
  server_count: number;
}

export interface ServerGroupCreate {
  name: string;
  description?: string | null;
  environment: string;
  server_ids: number[];
}

export interface GroupDeployRequest {
  bundle_id: number;
  backup: boolean;
  restart_nifi: boolean;
  dry_run: boolean;
  notes?: string | null;
  target_directory?: string | null;
}

export interface ServerHealth {
  server_id: number;
  reachable: boolean;
  disk_total_bytes: number | null;
  disk_used_bytes: number | null;
  disk_free_bytes: number | null;
  disk_used_percent: number | null;
  nar_dir_size_bytes: number | null;
  cpu_percent: number | null;
  memory_percent: number | null;
  nifi_status: string | null;
  nifi_version: string | null;
  uptime_seconds: number | null;
  warnings: string[];
  checked_at: string;
}

export interface NarBundleOut {
  id: number;
  bundle_group: string;
  artifact: string;
  version: string;
  filename: string;
  file_size: number;
  sha256: string;
  md5: string;
  status: string;
  is_pinned: boolean;
  tags: string;
  description: string | null;
  build_date: string | null;
  uploaded_by: string;
  uploaded_at: string;
  source: string;
}

export interface BundleGroup {
  bundle_group: string;
  artifact: string;
  versions: NarBundleOut[];
  latest_version: string;
  total_size: number;
}

export interface UploadResult {
  filename: string;
  success: boolean;
  bundle: NarBundleOut | null;
  error: string | null;
  replaced: boolean;
}

export interface DeploymentOut {
  id: number;
  bundle_id: number;
  server_id: number;
  status: string;
  dry_run: boolean;
  backup_created: boolean;
  restart_nifi: boolean;
  checksum_verified: boolean;
  target_directory: string | null;
  deployed_path: string | null;
  backup_path: string | null;
  deployed_by: string;
  notes: string | null;
  error_message: string | null;
  log: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  bundle: NarBundleOut | null;
  server: NiFiServerOut | null;
}

export interface CompatibilityWarning {
  level: "info" | "warning" | "error";
  message: string;
}

export interface CompatibilityReport {
  bundle_id: number;
  server_id: number;
  compatible: boolean;
  warnings: CompatibilityWarning[];
}

export interface BackupOut {
  id: number;
  server_id: number | null;
  deployment_id: number | null;
  filename: string;
  original_path: string;
  backup_path: string;
  file_size: number;
  sha256: string | null;
  bundle_artifact: string | null;
  bundle_version: string | null;
  created_by: string;
  created_at: string;
  restored_at: string | null;
  server_name: string | null;
}

export interface NexusServerOut {
  id: number;
  name: string;
  url: string;
  username: string | null;
  has_password: boolean;
  default_repository: string | null;
  is_enabled: boolean;
  sync_schedule: string | null;
  last_sync_at: string | null;
  created_at: string;
}

export interface NexusArtifact {
  repository: string;
  group: string;
  artifact: string;
  version: string;
  download_url: string;
  sha256: string | null;
  size: number | null;
}

export interface NexusRepository {
  name: string;
  format: string;
  type: string;
  url: string;
}

export interface RetentionPolicyOut {
  id: number;
  name: string;
  keep_latest: number;
  keep_days: number;
  is_enabled: boolean;
  dry_run: boolean;
  schedule: string;
  last_run_at: string | null;
  updated_at: string;
}

export interface RetentionCandidate {
  bundle_id: number;
  bundle_group: string;
  artifact: string;
  version: string;
  file_size: number;
  uploaded_at: string;
  reason: string;
  protected: boolean;
}

export interface RetentionPreview {
  candidates: RetentionCandidate[];
  total_count: number;
  total_size_bytes: number;
}

export interface RetentionRunOut {
  id: number;
  started_at: string;
  completed_at: string | null;
  dry_run: boolean;
  triggered_by: string;
  deleted_count: number;
  freed_bytes: number;
  report: string | null;
}

export interface AuditLogOut {
  id: number;
  timestamp: string;
  username: string;
  full_name: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  target_server: string | null;
  bundle: string | null;
  version: string | null;
  result: string;
  ip_address: string | null;
  user_agent: string | null;
  error_message: string | null;
  details: string | null;
}

export interface DashboardStats {
  total_servers: number;
  enabled_servers: number;
  total_bundles: number;
  active_versions: number;
  storage_bytes: number;
  total_deployments: number;
  failed_deployments: number;
  pending_cleanup: number;
  total_backups: number;
  backup_bytes: number;
}

export interface TimeSeriesPoint {
  date: string;
  count: number;
  bytes: number;
}

export interface TopBundle {
  artifact: string;
  bundle_group: string;
  deployment_count: number;
}

export interface DashboardCharts {
  uploads: TimeSeriesPoint[];
  deployments: TimeSeriesPoint[];
  storage_growth: TimeSeriesPoint[];
  top_bundles: TopBundle[];
}

export interface SettingItem {
  key: string;
  value: string | null;
  description: string | null;
}

export interface SettingsResponse {
  settings: SettingItem[];
  config: Record<string, unknown>;
}

export interface NotificationConfigOut {
  id: number;
  name: string;
  type: string;
  target: string;
  events: string;
  is_enabled: boolean;
  created_at: string;
}

export interface ApiTokenOut {
  id: number;
  name: string;
  prefix: string;
  role: string;
  created_by: string;
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
  is_active: boolean;
}

export interface ApiTokenCreated extends ApiTokenOut {
  token: string;
}

export interface RemoteNarFile {
  filename: string;
  size_bytes: number;
  modified: string | null;
}

export interface RestartResult {
  success: boolean;
  message: string;
  command: string;
  exit_code: number;
  stdout: string;
  stderr: string;
}

export interface GroupRestartNode {
  server_name: string;
  server_id: number;
  restart: RestartResult;
  bootstrap_wait_seconds: number;
  bootstrap_success: boolean;
}

export const NOTIFICATION_EVENTS = [
  "upload_completed",
  "deployment_completed",
  "deployment_failed",
  "rollback_completed",
  "cleanup_completed",
  "nexus_sync_completed",
] as const;
