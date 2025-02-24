resource "aws_cloudformation_stack" "sonrai_permission_firewall_stack" {
  name         = "SonraiCloudPermissionFirewall"
#add S3 URL to template_url below
  template_url = ""
  capabilities = [
    "CAPABILITY_NAMED_IAM"
  ]
}

