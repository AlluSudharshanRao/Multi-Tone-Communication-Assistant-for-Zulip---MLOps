variable "project_id_suffix" {
  description = "Course project id suffix for resource names, e.g. proj99"
  type        = string
}

variable "openstack_auth_url" {
  description = "OpenStack auth URL from Chameleon"
  type        = string
}

variable "openstack_region" {
  description = "OpenStack region name"
  type        = string
}

variable "openstack_tenant_name" {
  description = "Project/tenant name (optional if using application credential scoped to project or OS_PROJECT_ID)"
  type        = string
  default     = ""
}

variable "openstack_user_name" {
  description = "User name (omit when using application credentials)"
  type        = string
  default     = ""
}

variable "openstack_password" {
  description = "Password for username auth only (omit when using application credentials; never commit)"
  type        = string
  sensitive   = true
  default     = null
}

variable "application_credential_id" {
  description = "Application credential ID from Horizon (preferred over password for SSO accounts)"
  type        = string
  default     = ""
}

variable "application_credential_secret" {
  description = "Application credential secret (use TF_VAR_application_credential_secret; never commit)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "openstack_tenant_id" {
  description = "OpenStack project/tenant UUID from Horizon (optional; recommended with application credentials on Chameleon)"
  type        = string
  default     = ""
}

variable "instance_name" {
  description = "VM name suffix will be appended with project_id_suffix"
  type        = string
  default     = "mlops-k8s"
}

variable "flavor_name" {
  description = "OpenStack flavor, e.g. m1.large"
  type        = string
  default     = "m1.large"
}

variable "image_name" {
  description = "Glance image name for your Chameleon site (set in tfvars)"
  type        = string
}

variable "key_pair" {
  description = "Existing OpenStack key pair name for SSH"
  type        = string
}

variable "network_id" {
  description = "Tenant network UUID the VM attaches to"
  type        = string
}

variable "subnet_id" {
  description = "Subnet UUID for the public router interface (Horizon → Network → Subnets). Required when create_public_router is true."
  type        = string
  default     = ""

  validation {
    condition     = !var.create_public_router || var.subnet_id != ""
    error_message = "When create_public_router is true, subnet_id must be set to your tenant subnet UUID."
  }
}

variable "floating_ip_pool" {
  description = "External network name for allocating a floating IP (site-specific)"
  type        = string
  default     = "public"
}

variable "create_public_router" {
  description = "If true, create a router with external gateway and attach your project's first subnet. Set false if you already have a router connecting this network to public."
  type        = bool
  default     = true
}

variable "blazar_reservation_id" {
  description = "Chameleon Blazar *instance* reservation UUID (from lease → Reservations → id). When set, used as flavor_id (reservation:<id>); flavor_name is ignored."
  type        = string
  default     = ""
}

variable "install_k3s_cloud_init" {
  description = "If true, embed cloud-init that installs single-node k3s on first boot"
  type        = bool
  default     = false
}

variable "security_groups" {
  description = "Security group names for the instance (SSH + needed ports per your design)"
  type        = list(string)
}
