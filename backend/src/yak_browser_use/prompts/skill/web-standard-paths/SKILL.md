---
name: web-standard-paths
description: 标准 Web URL 路径清单（RFC/行业规范），包括根路径和 .well-known 路径
tags: [reference, web, standards]
linked_files: []
---

# Web 标准路径速查

## 根路径标准文件（禁止放 .well-known）

### 搜索引擎 & AI 爬虫
| 路径 | 规范 | 说明 |
|------|------|------|
| `/robots.txt` | RFC 9309 | 爬虫访问控制，声明 sitemap 地址 |
| `/sitemap.xml` | Sitemap 协议 | 站点索引地图，支持拆分 `/sitemap-01.xml` |
| `/llms.txt` / `/llms-full.txt` | AI 爬虫标准 | 大模型精简站点文档 |
| `/humans.txt` | 社区事实标准 | 网站开发人员、技术栈信息 |

### 移动端 & 应用绑定
| 路径 | 规范 | 说明 |
|------|------|------|
| `/apple-app-site-association` | Apple Universal Links | iOS App 唤起、Passkey 同步；**必须根路径** |
| `/manifest.webmanifest` | W3C PWA | PWA 应用清单（图标、名称、离线缓存） |
| `/favicon.ico` / `/favicon.svg` | 历史事实标准 | 浏览器默认读取根目录图标 |
| `/browserconfig.xml` | Microsoft | Windows 磁贴图标配置 |

### 邮件安全
| 路径 | 规范 | 说明 |
|------|------|------|
| `/mta-sts.txt` | RFC 8461 | 邮件 TLS 严格策略（新版根路径） |

### 证书/域名验证
| 路径 | 规范 | 说明 |
|------|------|------|
| `/pki-validation/` | CA/Browser Forum | 证书机构域名所有权校验目录 |
| `/.validate-domain.html` | 部分 SSL 厂商 | 自定义根路径校验文件 |

### 其他行业标准
| 路径 | 规范 | 说明 |
|------|------|------|
| `/opensearch.xml` | OpenSearch | 浏览器内置站内搜索插件 |
| `/ads.txt` / `/app-ads.txt` | IAB | 广告反欺诈，防止流量劫持 |
| `/privacy-policy` / `/terms` | 行业约定 | 隐私政策、服务条款通用路径 |

## .well-known 路径（RFC 5785 注册）

| 路径 | 规范 | 说明 |
|------|------|------|
| `/.well-known/change-password` | W3C WebAppSec | 密码修改入口 URL |
| `/.well-known/security.txt` | RFC 9116 | 安全研究员联系和漏洞披露信息 |
| `/.well-known/webauthn` | W3C WebAuthn | Web 认证（Passkey）相关资源 |
| `/.well-known/gpc.json` | Global Privacy Control | 全球隐私控制配置 |
| `/.well-known/openid-configuration` | OpenID Connect | OIDC 发现文档 |
| `/.well-known/acme-challenge/` | ACME RFC 8555 | Let's Encrypt 等证书自动签发验证 |
| `/.well-known/assetlinks.json` | Android | Android App Links 数字资产链接 |
| `/.well-known/mta-sts.txt` | RFC 8461 | 邮件 TLS 策略（旧版路径） |
| `/.well-known/dnt/` | W3C DNT | Do Not Track 策略（已废弃但仍有部署） |
| `/.well-known/posh/` | RFC 7711 | XMPP 等协议的主机元数据 |
| `/.well-known/nodeinfo` | ActivityPub | Fediverse 实例信息 |
| `/.well-known/host-meta` / `/.well-known/host-meta.json` | RFC 6415 | Web 主机元数据 |
| `/.well-known/time` | NTP 补充 | 时间服务发现 |

## WebAppSec 响应头（非路径，同安全体系补充）

- `Content-Security-Policy` — CSP 内容安全策略
- `Referrer-Policy` — 引用来源策略
- `Permissions-Policy` — 权限策略（原 Feature Policy）
- `Trusted Types` — DOM XSS 防护
- `Subresource Integrity` (SRI) — 子资源完整性校验
- `Upgrade-Insecure-Requests` — 强制 HTTPS
