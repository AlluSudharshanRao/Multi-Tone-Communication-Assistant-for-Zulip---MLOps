resource "kubernetes_namespace" "zulip" {
  metadata {
    name = "zulip"
  }
}

resource "kubernetes_namespace" "ml_platform" {
  metadata {
    name = "ml-platform"
  }
}

resource "kubernetes_namespace" "ml_training" {
  metadata {
    name = "ml-training"
  }
}

resource "kubernetes_namespace" "ml_serving" {
  metadata {
    name = "ml-serving"
  }
}

resource "kubernetes_namespace" "ml_data" {
  metadata {
    name = "ml-data"
  }
}

resource "kubernetes_namespace" "monitoring" {
  metadata {
    name = "monitoring"
  }
}
