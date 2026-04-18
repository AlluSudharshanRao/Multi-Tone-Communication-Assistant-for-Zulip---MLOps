variable "kubeconfig_path" {
  description = "Path to kubeconfig (e.g. ~/.kube/config)"
  type        = string
  default     = "~/.kube/config"
}

variable "kube_context" {
  description = "Kube context name; leave empty for current context"
  type        = string
  default     = ""
}

variable "project_id_suffix" {
  description = "Course project id suffix, e.g. proj99 — used in Helm release names"
  type        = string
}

variable "deploy_zulip" {
  description = "If true, install Zulip via Helm (requires local chart path)"
  type        = bool
  default     = false
}

variable "zulip_helm_chart_path" {
  description = "Filesystem path to vendored docker-zulip chart directory (helm/zulip)"
  type        = string
  default     = ""
}

variable "zulip_values_files" {
  description = "Extra Helm values files (site hostname, ingress, resources)"
  type        = list(string)
  default     = []
}

variable "deploy_mlflow_helm" {
  description = "If true, install MLflow via Bitnami Helm chart (heavier than k8s/platform/mlflow kustomize)"
  type        = bool
  default     = false
}

variable "mlflow_helm_release_name" {
  type    = string
  default = "mlflow"
}

variable "mlflow_chart_version" {
  description = "Bitnami mlflow chart version (empty = latest resolved at plan/apply time)"
  type        = string
  default     = ""
}
