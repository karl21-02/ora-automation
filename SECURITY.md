# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please follow these steps:

### DO NOT

- Open a public GitHub issue
- Disclose the vulnerability publicly before it's fixed

### DO

1. **Email us** at security@example.com (replace with actual contact)
2. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial Assessment**: Within 1 week
- **Resolution**: Depends on severity
  - Critical: ASAP (target < 7 days)
  - High: < 30 days
  - Medium: < 60 days
  - Low: Next release

## Security Best Practices

When deploying Ora Automation:

### Environment Variables

- Never commit `.env` files
- Use secrets management in production
- Rotate credentials regularly

### API Keys & Tokens

- Use minimal required permissions
- Set expiration where possible
- Monitor for unauthorized usage

### Database

- Use strong passwords
- Enable SSL/TLS connections
- Regular backups
- Restrict network access

### Docker Deployment

- Don't run containers as root
- Use read-only filesystems where possible
- Keep images updated
- Scan for vulnerabilities

### Network

- Use HTTPS in production
- Configure CORS properly
- Use firewalls/security groups
- Enable rate limiting

## Known Security Considerations

### LLM Integration

- API keys are stored in environment variables
- Prompts may contain sensitive project data
- Review LLM outputs before publishing

### GitHub Integration

- Webhook secrets should be strong
- Private key should be secured
- Review repository access permissions

### Notion Integration

- API token has broad access
- Review what data is published
- Consider using a dedicated integration

## Security Updates

Security updates will be announced via:
- GitHub Security Advisories
- Release notes

## Acknowledgments

We appreciate responsible disclosure and will acknowledge security researchers who help improve our security.
