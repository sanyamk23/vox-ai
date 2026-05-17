variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "public_key_path" {
  description = "Path to your local SSH public key (e.g. ~/.ssh/id_rsa.pub)"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

variable "repo_url" {
  description = "Git repository HTTPS URL. For private repos use a token: https://<TOKEN>@github.com/org/repo.git"
  type        = string
}

variable "domain" {
  description = "Domain pointing at the server (e.g. app.example.com). Used for Caddy SSL, Django ALLOWED_HOSTS, and CSRF config."
  type        = string
}

variable "twilio_account_sid" {
  description = "Twilio Account SID (starts with AC...)"
  type        = string
}

variable "twilio_auth_token" {
  description = "Twilio Auth Token"
  type        = string
  sensitive   = true
}

variable "twilio_phone_number" {
  description = "Twilio phone number in E.164 format (e.g. +15551234567)"
  type        = string
}

variable "gemini_api_key" {
  description = "Google Gemini API key"
  type        = string
  sensitive   = true
}

variable "django_secret_key" {
  description = "Django SECRET_KEY. Generate with: python -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\""
  type        = string
  sensitive   = true
}
