terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ─── LOCALS ───────────────────────────────────────────────────────────────────
locals {
  # Derive private key path from public key path (strips .pub suffix).
  # Used in outputs so terraform apply prints a ready-to-use SSH command.
  private_key_path = trimsuffix(pathexpand(var.public_key_path), ".pub")
}

# ─── AMI ──────────────────────────────────────────────────────────────────────
# Ubuntu 22.04 LTS ARM64 — required for t4g (Graviton) instances
data "aws_ami" "ubuntu_arm" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-arm64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "architecture"
    values = ["arm64"]
  }
}

# ─── SSH KEY ──────────────────────────────────────────────────────────────────
resource "aws_key_pair" "app" {
  key_name   = "vox-ai-key"
  # pathexpand() resolves ~ to the actual home directory
  public_key = file(pathexpand(var.public_key_path))
}

# ─── SECURITY GROUP ───────────────────────────────────────────────────────────
resource "aws_security_group" "app" {
  name        = "vox-ai-sg"
  description = "Allow SSH, HTTP, HTTPS inbound; all outbound"

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "vox-ai-sg" }
}

# ─── EC2 INSTANCE ─────────────────────────────────────────────────────────────
resource "aws_instance" "app" {
  ami                    = data.aws_ami.ubuntu_arm.id
  instance_type          = "t4g.micro" # 1 vCPU, 1 GB RAM, Graviton — ~$6/mo
  key_name               = aws_key_pair.app.key_name
  vpc_security_group_ids = [aws_security_group.app.id]

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 20
    encrypted             = true
    delete_on_termination = true
  }

  user_data = templatefile("${path.module}/user_data.sh", {
    repo_url            = var.repo_url
    domain              = var.domain
    twilio_account_sid  = var.twilio_account_sid
    twilio_auth_token   = var.twilio_auth_token
    twilio_phone_number = var.twilio_phone_number
    gemini_api_key      = var.gemini_api_key
    django_secret_key   = var.django_secret_key
  })

  tags = { Name = "vox-ai-app" }
}

# ─── ELASTIC IP ───────────────────────────────────────────────────────────────
# Keeps the IP stable across instance reboots — required for Twilio webhook URL
resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"

  tags = { Name = "vox-ai-eip" }
}
