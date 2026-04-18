# Chameleon OpenStack: VM, network, floating IP. Auth via application credential (preferred) or user/pass.
# Credentials: pick ONE approach.
# 1) Recommended (SSO / college login): application credential from Horizon → Identity → Application Credentials.
#    Set TF_VAR_application_credential_id / TF_VAR_application_credential_secret, or use env vars:
#    OS_AUTH_TYPE=v3applicationcredential, OS_APPLICATION_CREDENTIAL_ID, OS_APPLICATION_CREDENTIAL_SECRET,
#    OS_AUTH_URL, OS_REGION_NAME (see Chameleon clouds.yaml).
# 2) Username + password: set openstack_user_name, openstack_password, openstack_tenant_name in tfvars.
# If auth fields below are empty, the provider reads standard OS_* environment variables.
provider "openstack" {
  auth_url = var.openstack_auth_url
  region   = var.openstack_region

  tenant_id   = var.openstack_tenant_id != "" ? var.openstack_tenant_id : null
  tenant_name = var.openstack_tenant_name != "" ? var.openstack_tenant_name : null
  user_name   = var.openstack_user_name != "" ? var.openstack_user_name : null
  password    = var.openstack_password

  application_credential_id     = var.application_credential_id != "" ? var.application_credential_id : null
  application_credential_secret = var.application_credential_secret != "" ? var.application_credential_secret : null
}
