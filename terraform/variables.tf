variable "region" {
  description = "AWS region (same as RDS)"
  type        = string
  default     = "ap-south-1"
}

variable "vpc_id" {
  description = "VPC that hosts RDS / the Teleport DB service"
  type        = string
}

# ---- The public URL ---------------------------------------------------------
variable "domain_name" {
  description = "Root domain you own (registered at your registrar), e.g. example.com"
  type        = string
}

variable "subdomain" {
  description = "Host label for the UI; final URL = <subdomain>.<domain_name>"
  type        = string
  default     = "teleport-demo"
}

# ---- EC2 --------------------------------------------------------------------
variable "key_name" {
  description = "Existing EC2 key pair for SSH"
  type        = string
}

variable "instance_type" {
  type    = string
  default = "t3.small"
}

variable "ssh_cidr" {
  description = "CIDR allowed to SSH to the instance"
  type        = string
}

variable "app_port" {
  description = "Port Streamlit listens on"
  type        = number
  default     = 8501
}

# ---- Teleport / app ---------------------------------------------------------
variable "teleport_proxy" {
  type    = string
}

variable "teleport_iam_token" {
  description = "Name of the Teleport IAM-join token for the EC2 bot (create with tctl)"
  type        = string
  default     = "ec2-ui-iam-token"
}

variable "db_resource" {
  description = "Teleport database resource name"
  type        = string
  default     = "teleport-demo-db"
}

variable "db_name" {
  type    = string
  default = "opsdb"
}

variable "db_user" {
  type    = string
  default = "readonly_agent"
}

variable "bedrock_model_id" {
  type    = string
  default = "global.anthropic.claude-opus-4-5-20251101-v1:0"
}

variable "ec2_role_name" {
  description = "IAM role name for the EC2 instance (referenced by the Teleport IAM-join token)"
  type        = string
  default     = "teleport-demo-ui-ec2-role"
}

variable "name_prefix" {
  type    = string
  default = "teleport-demo-ui"
}
