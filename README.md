# Caddis API Automation

A comprehensive automation solution for extracting data from Caddis API and uploading it to Google Sheets using Google Cloud Run Jobs.

## 🚀 Features

- **Automated Data Extraction**: Fetches articles and prices from Caddis API endpoints
- **Google Sheets Integration**: Uploads processed data to Google Sheets
- **Cloud-Native**: Runs on Google Cloud Run Jobs with Workload Identity Federation
- **CI/CD Pipeline**: Automated build and deployment with GitHub Actions
- **Containerized**: Docker-based deployment for consistency and portability
- **Configurable**: Supports configuration via environment variables and YAML files

## 📋 Prerequisites

1. **Google Cloud Project** with billing enabled
2. **GitHub Repository** with appropriate secrets configured
3. **Caddis API** credentials
4. **Google Sheets** document with proper permissions

## 🔧 Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   GitHub        │────▶│   Cloud Build   │────▶│   Artifact      │
│   Actions       │     │   / CI/CD       │     │   Registry      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Caddis API    │◀────│   Cloud Run     │◀────│   Container     │
│   Endpoints     │     │   Job           │     │   Image         │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │   Google        │
                        │   Sheets        │
                        └─────────────────┘
```

## 🛠️ Setup Instructions

> **📖 Para configuración completa paso a paso, consulta [SETUP_GUIDE.md](SETUP_GUIDE.md)**

### Configuración Rápida (Proyecto Existente)

1. **Ejecutar script de configuración**:
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```

2. **Configurar Google Sheets**:
   - Crear hoja de cálculo en Google Sheets
   - Compartir con: `caddis-automation-sa@TU_PROJECT_ID.iam.gserviceaccount.com`
   - Dar permisos de Editor

3. **Configurar GitHub Secrets** (ver SETUP_GUIDE.md para lista completa)

4. **Hacer push** para desplegar automáticamente

5. **Configurar Cloud Scheduler** desde la consola de Google Cloud

## 🚀 Deployment

### Automatic Deployment (GitHub Actions)

1. **Push to master branch**:
   ```bash
   git add .
   git commit -m "Deploy caddis automation"
   git push origin master
   ```

2. **Monitor the deployment** in GitHub Actions tab

### Manual Deployment

1. **Build and push Docker image**:
   ```bash
   docker build -t us-central1-docker.pkg.dev/PROJECT_ID/caddis-automation/caddis-automation:latest .
   docker push us-central1-docker.pkg.dev/PROJECT_ID/caddis-automation/caddis-automation:latest
   ```

2. **Deploy Cloud Run Job**:
   ```bash
   gcloud run jobs replace job.yaml --region=us-central1
   ```

## ⏰ Programación de Ejecución

### Cloud Scheduler + Cloud Run Jobs (Configurar desde Google Cloud Console)

1. **Crear un Cloud Scheduler Job desde la consola o CLI**:
   ```bash
   gcloud scheduler jobs create http caddis-automation-scheduler \
     --schedule="0 */6 * * *" \
     --uri="https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/PROJECT_ID/jobs/caddis-automation:run" \
     --http-method=POST \
     --oauth-service-account-email=caddis-automation-sa@PROJECT_ID.iam.gserviceaccount.com \
     --location=us-central1
   ```

2. **Horarios de ejemplo**:
   - Cada 6 horas: `"0 */6 * * *"`
   - Diariamente a las 2 AM: `"0 2 * * *"`
   - Cada lunes a las 8 AM: `"0 8 * * 1"`
   - Cada hora durante horario laboral: `"0 9-17 * * 1-5"`

### Ejecución Manual

```bash
# Ejecutar inmediatamente
gcloud run jobs execute caddis-automation --region=us-central1

# Verificar el estado
gcloud run jobs describe caddis-automation --region=us-central1
```

> **Nota**: Para una guía completa de configuración paso a paso, consulta [SETUP_GUIDE.md](SETUP_GUIDE.md)

## 🔍 Monitoring and Troubleshooting

### Check Job Status
```bash
gcloud run jobs describe caddis-automation --region=us-central1
```

### View Job Logs
```bash
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=caddis-automation" --limit=50
```

### Monitor Scheduled Executions
```bash
# Ver jobs programados
gcloud scheduler jobs list --location=us-central1

# Ver logs del scheduler
gcloud logging read "resource.type=cloud_scheduler_job" --limit=20

# Ejecutar manualmente un job programado
gcloud scheduler jobs run caddis-automation-scheduler --location=us-central1
```

### Common Issues

1. **Authentication Errors**:
   - Verify Workload Identity Federation setup
   - Check service account permissions
   - Ensure GitHub secrets are correctly configured

2. **API Rate Limiting**:
   - Adjust `rate_limit_delay` in config.yaml
   - Monitor API usage in Caddis dashboard

3. **Memory Issues**:
   - Increase memory limits in job.yaml
   - Consider processing data in batches

## 📊 Data Flow

1. **Articles Extraction**: `/v1/articulos?pagina={page}`
   - Iterates through all pages until empty
   - Extracts: `id`, `sku`, `nombre`, `tipo`, `marca`, `grupo`

2. **Prices Extraction**: `/v1/articulos/precios?pagina={page}&lista={lista}`
   - Iterates through all pages and price lists
   - Extracts: `sku`, `iva_tasa`, `precio_unitario`

3. **Data Processing**:
   - Combines data by SKU
   - Maps to 30 columns as specified
   - Handles missing data gracefully

4. **Google Sheets Upload**:
   - Clears existing data
   - Uploads new data with headers
   - Maintains data integrity

## 📈 Price List Mapping

| ID | Column Name              |
|----|--------------------------|
| 1  | Minorista Ars           |
| 2  | Dealer Ars              |
| 3  | Dealer 1 Ars            |
| 5  | Dealer 30d Ars          |
| 7  | Nautica Dealer Usd      |
| 8  | Dealer 60d Ars          |
| 9  | Mino Ml Premium Ars     |
| 10 | Sub Distribuidor Usd    |
| 11 | Dealer 55mkup Ars       |
| 12 | Dealer 50mkup Ars       |
| 13 | Anterior Mino Ars       |
| 14 | Mixta Ars               |
| 15 | Grouping 70mkup Ars     |
| 16 | Dealer Cencosud Ars     |
| 17 | Nautica Dealer 1 Usd    |
| 18 | Nautica Dealer Ars      |
| 19 | Nautica Dealer 1 Ars    |
| 20 | Fob Standard Usd        |
| 21 | Dealer Golf Ars         |
| 22 | Gpsmundo Srl            |
| 23 | Dealer Meli Ars         |
| 24 | Dealer 5g Ars           |
| 25 | Fob Supplier Llc        |
| 33 | Dealer Diggit Ars       |

## 🔧 Configuration

### Environment Variables
- `CADDIS_API_URL`: Base URL for Caddis API
- `CADDIS_API_KEY`: API key for authentication
- `GOOGLE_SHEETS_ID`: Google Sheets document ID
- `PRICE_LISTS`: Comma-separated list of price list IDs

### Configuration File (config.yaml)
```yaml
caddis_api_url: "https://api.caddis.com"
google_sheets_id: "your-sheets-id"
price_lists: [1, 2, 3, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 33]
rate_limit_delay: 0.1
request_timeout: 30
max_retries: 3
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:
1. Check the troubleshooting section
2. Review Cloud Run Job logs
3. Create an issue in the GitHub repository

---

**Note**: Replace placeholder values (PROJECT_ID, API keys, etc.) with your actual values before deployment.