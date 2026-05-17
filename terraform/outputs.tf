output "public_ip" {
  description = "Static public IP — point your domain A record here"
  value       = aws_eip.app.public_ip
}

output "ssh_command" {
  description = "SSH into the instance to check logs or debug"
  value       = "ssh -i ${local.private_key_path} ubuntu@${aws_eip.app.public_ip}"
}

output "app_url" {
  description = "Share this URL with users — your main website"
  value       = "https://${var.domain}"
}

output "twilio_voice_webhook" {
  description = "Set this as your Twilio phone number Voice webhook (HTTP POST)"
  value       = "https://${var.domain}/outgoing-call/"
}

output "admin_url" {
  description = "Django admin panel (internal use only)"
  value       = "https://${var.domain}/admin/"
}

output "next_steps" {
  description = "Post-deploy checklist printed after terraform apply"
  value       = <<-EOT

    ── Deployment checklist ────────────────────────────────────────────────────

    1. Point your domain A record to: ${aws_eip.app.public_ip}
       (DNS usually propagates within 1–5 min)

    2. Wait ~5 min for Docker images to build on the instance.
       Check progress:
         ssh -i ${local.private_key_path} ubuntu@${aws_eip.app.public_ip}
         tail -f /var/log/user-data.log

    3. Set Twilio Voice webhook in the Twilio console:
         URL  : https://${var.domain}/outgoing-call/
         Method: HTTP POST

    4. Open your app:
         https://${var.domain}

    ────────────────────────────────────────────────────────────────────────────
  EOT
}
