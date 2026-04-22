resource "helm_release" "mlflow" {
  count = var.deploy_mlflow_helm ? 1 : 0

  name             = "${var.mlflow_helm_release_name}-${var.project_id_suffix}"
  namespace        = kubernetes_namespace.ml_platform.metadata[0].name
  create_namespace = false

  repository = "oci://registry-1.docker.io/bitnamicharts"
  chart      = "mlflow"
  version    = var.mlflow_chart_version != "" ? var.mlflow_chart_version : null
}
