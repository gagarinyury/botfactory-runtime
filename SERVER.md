# Server Documentation

## 🖥️ Server Information

**Provider:** Contabo
**OS:** Ubuntu 24.04.3 LTS
**IP:** 207.180.199.169
**IPv6:** 2a02:c207:2281:3437::1
**Domain:** profy.top

## 🔐 Access

### SSH Access
```bash
# Local alias command
server2

# Or full SSH command
ssh root@207.180.199.169
```

**User:** root
**Key:** SSH key configured in local ~/.ssh/config as `server2`

## 🌐 Domain & SSL

### Domain Configuration
- **Main Domain:** profy.top
- **SSL Provider:** Sectigo (valid until April 9, 2026)
- **Certificate Locations:**
  - Main cert: `/etc/ssl/sectigo/profy_top.crt`
  - Private key: `/etc/ssl/sectigo/profy_top.key`
  - Full chain: `/etc/ssl/sectigo/fullchain.pem`
  - Intermediate: `/etc/ssl/sectigo/SectigoRSADomainValidationSecureServerCA.crt`
  - Root CA: `/etc/ssl/sectigo/USERTrustRSAAAACA.crt`

### Local Certificate Sources
Certificates are stored locally at:
```
/Users/yurygagarin/Documents/2_Business/Certificates/SSL Сертификаты/
```

## 🚢 Deployed Services

### Web Server (Nginx)
- **Port 80:** HTTP (redirects to HTTPS)
- **Port 443:** HTTPS with Sectigo SSL
- **Config:** `/etc/nginx/sites-available/profy.top`

### Current Applications

| Service | Port | URL Path | Description |
|---------|------|----------|-------------|
| Main Website | 443 | `/` | Static HTML/PHP site |
| Psychology Section | 443 | `/psy/` | Psychology subsection |
| Contact API | 3001 | `/api/` | Contact form backend |
| Terminal Access | 2222 | `/terminal` | ttyd web terminal (auth required) |
| Code Server | 8080 | `/code/` | VS Code in browser |
| Bot Factory Runtime | 8000 | `/bot/` | **Bot Factory API** |
| Ollama LLM | 11434 | - | Local LLM server |

### Process Management (PM2)
```bash
pm2 list
pm2 logs simple_llm
pm2 restart simple_llm
```

Current PM2 processes:
- `simple_llm` (port 3001) - Contact form API

## 🔧 System Commands

### Service Management
```bash
# Nginx
sudo systemctl status nginx
sudo systemctl reload nginx
sudo nginx -t

# Check ports
ss -tlnp

# System info
df -h          # Disk usage
free -h        # Memory usage
htop           # Process monitor
```

## 📦 Bot Factory Runtime Deployment

### Current Setup
- **Port:** 8000 (internal)
- **Public URL:** https://profy.top/bot/
- **Proxy:** Configured in nginx

### Deployment Steps
1. **Copy project to server:**
   ```bash
   scp -r botfactory-runtime/ server2:/opt/
   ```

2. **Install dependencies:**
   ```bash
   server2 'cd /opt/botfactory-runtime && pip install .'
   ```

3. **Configure environment:**
   ```bash
   server2 'cd /opt/botfactory-runtime && cp .env.example .env'
   # Edit .env with actual values
   ```

4. **Start with PM2:**
   ```bash
   server2 'cd /opt/botfactory-runtime && pm2 start "uvicorn runtime.app:app --host 0.0.0.0 --port 8000" --name botfactory-runtime'
   ```

5. **Save PM2 configuration:**
   ```bash
   server2 'pm2 save && pm2 startup'
   ```

### Environment Variables
```bash
DATABASE_URL=postgresql+psycopg://dev:dev@localhost:5432/botfactory
REDIS_URL=redis://localhost:6379/0
TELEGRAM_DOMAIN=https://profy.top
```

## 🐳 Docker Setup (Alternative)

If using Docker instead of PM2:

```bash
# Build and run
server2 'cd /opt/botfactory-runtime && docker-compose up -d'

# Check logs
server2 'cd /opt/botfactory-runtime && docker-compose logs -f'
```

## 🛡️ Security Notes

- **SSH:** Key-based authentication only
- **Nginx:** Security headers configured
- **SSL:** A+ grade configuration with Sectigo certificates
- **Firewall:** UFW enabled (ports 22, 80, 443 open)
- **Updates:** 2 system updates available (run `apt list --upgradable`)

## 📝 Maintenance

### SSL Certificate Renewal
Sectigo certificates expire April 9, 2026. Renewal process:
1. Obtain new certificates from Sectigo
2. Copy to `/etc/ssl/sectigo/`
3. Recreate fullchain: `cat profy_top.crt SectigoRSA*.crt USERTrust*.crt > fullchain.pem`
4. Reload nginx: `systemctl reload nginx`

### Backup Important Files
- `/etc/nginx/sites-available/` - Nginx configs
- `/etc/ssl/sectigo/` - SSL certificates
- PM2 process list: `pm2 save`

### Log Locations
- **Nginx:** `/var/log/nginx/`
- **PM2:** `~/.pm2/logs/`
- **System:** `/var/log/syslog`

## 🆘 Emergency Contacts

**Hosting Provider:** Contabo
**Support:** support@contabo.com

## 📊 Server Stats

- **CPU:** x86_64
- **Memory:** 3% usage
- **Disk:** 5.9% of 386.42GB used
- **Load:** 0.01
- **Uptime:** Check with `uptime`

---

**Last Updated:** September 2025
**Maintainer:** Infrastructure Team