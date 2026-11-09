output "url" {
  description = "Public HTTPS URL for the UI"
  value       = "https://${local.fqdn}"
}

output "name_servers" {
  description = "Set THESE as the NS records for your domain at your registrar"
  value       = aws_route53_zone.primary.name_servers
}

output "alb_dns_name" {
  value = aws_lb.ui.dns_name
}

output "ec2_public_ip" {
  value = aws_instance.ui.public_ip
}

output "ec2_instance_id" {
  value = aws_instance.ui.id
}

output "ec2_role_arn" {
  description = "Use this ARN in the Teleport IAM-join token allow rule"
  value       = aws_iam_role.ec2.arn
}
