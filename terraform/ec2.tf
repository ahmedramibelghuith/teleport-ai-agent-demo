resource "aws_instance" "ui" {
  ami                         = data.aws_ssm_parameter.al2023.value
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.ec2.id]
  iam_instance_profile        = aws_iam_instance_profile.ec2.name
  key_name                    = var.key_name
  associate_public_ip_address = true

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    region             = var.region
    bedrock_model_id   = var.bedrock_model_id
    teleport_proxy     = var.teleport_proxy
    teleport_iam_token = var.teleport_iam_token
    db_resource        = var.db_resource
    db_name            = var.db_name
    db_user            = var.db_user
    app_port           = var.app_port
  })

  # Re-provision if the bootstrap script changes
  user_data_replace_on_change = true

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }

  tags = { Name = var.name_prefix }
}
