# Jekyll Deployment Guide

This guide covers deploying the Jekyll website to GitHub Pages or other hosting platforms.

## Prerequisites

- GitHub account
- Git installed
- Ruby 2.7+ and Jekyll (for local testing)
- Your API deployed and URL available

## Option 1: GitHub Pages (Recommended)

### 1. Create GitHub Repository

```bash
cd jekyll-site

# Initialize git if not already
git init

# Create .gitignore
cat > .gitignore << EOF
_site/
.sass-cache/
.jekyll-cache/
.jekyll-metadata
.DS_Store
EOF
```

### 2. Configure API URL

Edit `_config.yml`:

```yaml
title: Meshtastic Network Explorer
description: Public explorer for federated Meshtastic network data
baseurl: ""
url: "https://yourusername.github.io"  # Change this

# API configuration
api_url: "https://your-app.fly.dev"  # Change this to your API URL

# Map settings (adjust as needed)
map:
  default_center: [37.0902, -95.7129]  # Your network's center
  default_zoom: 5
```

### 3. Test Locally (Optional)

```bash
# Install dependencies
bundle install

# Run local server
bundle exec jekyll serve

# Visit http://localhost:4000
```

### 4. Create GitHub Repository

Go to https://github.com/new and create a new repository named:
- `yourusername.github.io` (for user site)
- OR `meshtastic-explorer` (for project site)

### 5. Push to GitHub

```bash
git add .
git commit -m "Initial Jekyll site for federated Meshtastic"
git branch -M main
git remote add origin https://github.com/yourusername/your-repo.git
git push -u origin main
```

### 6. Enable GitHub Pages

1. Go to your repository on GitHub
2. Click **Settings** → **Pages**
3. Under **Source**, select:
   - Branch: `main`
   - Folder: `/ (root)`
4. Click **Save**

Your site will be available at:
- User site: `https://yourusername.github.io`
- Project site: `https://yourusername.github.io/meshtastic-explorer`

### 7. Update baseurl (Project Sites Only)

If using a project site, update `_config.yml`:

```yaml
baseurl: "/meshtastic-explorer"
```

And commit:

```bash
git add _config.yml
git commit -m "Update baseurl for project site"
git push
```

## Option 2: Custom Domain

### 1. Configure DNS

Add DNS records for your domain:

```
Type: A
Name: @
Value: 185.199.108.153

Type: A
Name: @
Value: 185.199.109.153

Type: A
Name: @
Value: 185.199.110.153

Type: A
Name: @
Value: 185.199.111.153

Type: CNAME
Name: www
Value: yourusername.github.io
```

### 2. Add CNAME File

```bash
echo "your-domain.com" > CNAME
git add CNAME
git commit -m "Add custom domain"
git push
```

### 3. Enable HTTPS

In GitHub repository settings:
1. Go to **Settings** → **Pages**
2. Under **Custom domain**, enter your domain
3. Check **Enforce HTTPS**

Wait for DNS propagation (can take 24-48 hours).

## Option 3: Netlify

### 1. Push to GitHub

Follow steps 1-5 from GitHub Pages section.

### 2. Connect to Netlify

1. Go to [Netlify](https://netlify.com)
2. Click **New site from Git**
3. Connect your GitHub repository
4. Build settings:
   - Build command: `jekyll build`
   - Publish directory: `_site`

### 3. Environment Variables

In Netlify dashboard, go to **Site settings** → **Environment variables**:

```
JEKYLL_ENV=production
```

### 4. Deploy

Netlify will automatically deploy on every push to main.

## Option 4: Vercel

### 1. Install Vercel CLI

```bash
npm install -g vercel
```

### 2. Deploy

```bash
cd jekyll-site
vercel
```

Follow prompts to link your project.

### 3. Configure

Create `vercel.json`:

```json
{
  "buildCommand": "jekyll build",
  "outputDirectory": "_site",
  "devCommand": "jekyll serve --port $PORT",
  "installCommand": "bundle install"
}
```

## Configuration

### API URL

The most important configuration is the API URL in `_config.yml`:

```yaml
api_url: "https://your-app.fly.dev"
```

This tells the JavaScript code where to fetch data.

### Map Center

Adjust the default map center to your network's location:

```yaml
map:
  default_center: [40.7128, -74.0060]  # New York City
  default_zoom: 10
```

### Privacy Settings

Configure coordinate precision:

```yaml
privacy:
  coordinate_precision: 3  # 3 decimals ≈ 100m precision
  hide_private_messages: true
```

### Site Branding

Update site title and description:

```yaml
title: Your Network Name
description: Public explorer for our Meshtastic mesh network
```

## Customization

### Custom Theme

To change colors, edit `assets/css/main.css`:

```css
:root {
    --primary-color: #3b82f6;  /* Change primary color */
    --secondary-color: #8b5cf6;
    /* ... */
}
```

### Add Logo

1. Add logo image to `assets/images/logo.png`
2. Edit `_layouts/default.html`:

```html
<h1 class="site-title">
    <img src="{{ '/assets/images/logo.png' | relative_url }}" alt="Logo" style="height: 30px;">
    <a href="{{ '/' | relative_url }}">{{ site.title }}</a>
</h1>
```

### Add Analytics

Add Google Analytics or similar to `_layouts/default.html`:

```html
<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-XXXXXXXXXX');
</script>
```

### Add About Page

Create `about.md`:

```markdown
---
layout: default
title: About
---

# About This Network

Information about your Meshtastic network...
```

Add to navigation in `_layouts/default.html`.

## Updating the Site

### Regular Updates

```bash
cd jekyll-site

# Make changes to files
# ...

# Commit and push
git add .
git commit -m "Update site"
git push
```

GitHub Pages will automatically rebuild and deploy.

### Force Rebuild

If auto-deploy isn't working:

```bash
git commit --allow-empty -m "Trigger rebuild"
git push
```

## Troubleshooting

### Site Not Loading Data

Check browser console (F12) for errors:

1. **CORS errors**: API needs to allow requests from your domain
   - Add to API `main.py`:
   ```python
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["https://your-domain.com"],
       ...
   )
   ```

2. **404 on API**: Check API URL in `_config.yml`

3. **Mixed content**: Ensure API uses HTTPS

### Build Failures

Check build logs in GitHub Actions or hosting platform.

Common issues:
- Missing dependencies in `Gemfile`
- Syntax errors in Liquid templates
- Invalid YAML in front matter

### JavaScript Not Working

1. Check browser console for errors
2. Verify CDN libraries are loading:
   - Leaflet
   - D3.js
   - Marker cluster

3. Test API directly:
```bash
curl https://your-api.fly.dev/v1/stats
```

### Performance Issues

#### Optimize Images

```bash
# Install imageoptim or similar
brew install imageoptim-cli

# Optimize
imageoptim assets/images/*
```

#### Enable Caching

Add to `_config.yml`:

```yaml
sass:
  style: compressed

plugins:
  - jekyll-sitemap
```

#### Use CDN

Consider using a CDN like Cloudflare for:
- Faster asset delivery
- DDoS protection
- Automatic minification

## Monitoring

### Uptime Monitoring

Use services like:
- [UptimeRobot](https://uptimerobot.com) (free)
- [Pingdom](https://www.pingdom.com)
- [StatusCake](https://www.statuscake.com)

Monitor:
- Site homepage
- API health endpoint
- Map page loading

### Analytics

Track usage with:
- Google Analytics
- Plausible (privacy-friendly)
- Fathom Analytics

Key metrics:
- Page views
- User locations
- Popular pages
- Load times

## Security

### Content Security Policy

Add to `_includes/head.html`:

```html
<meta http-equiv="Content-Security-Policy"
      content="default-src 'self';
               script-src 'self' 'unsafe-inline' https://unpkg.com https://d3js.org;
               style-src 'self' 'unsafe-inline' https://unpkg.com;
               connect-src 'self' https://your-api.fly.dev;
               img-src 'self' https: data:;">
```

### HTTPS Only

Ensure HTTPS is enforced:
- GitHub Pages: Check "Enforce HTTPS" in settings
- Custom domain: Use HTTPS-only DNS records

### API Rate Limiting

Consider adding rate limiting to public API endpoints to prevent abuse.

## Best Practices

1. **Version Control**: Always commit changes before deploying
2. **Test Locally**: Run `jekyll serve` before pushing
3. **Backup**: Keep backups of `_config.yml` and custom pages
4. **Monitor**: Set up uptime monitoring
5. **Update**: Keep Jekyll and plugins updated
6. **Document**: Add comments to custom code
7. **Optimize**: Compress images and minify CSS/JS

## Next Steps

- [Collector Setup Guide](collector-setup.md) - Set up data collectors
- [API Deployment Guide](api-deployment.md) - Deploy central API
- [Integration Guide](integration.md) - Integrate with your code
