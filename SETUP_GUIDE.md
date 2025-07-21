# 🚀 Guía de Configuración - Proyecto Google Cloud Existente

Esta guía asume que ya tienes un proyecto de Google Cloud creado y configurado.

## 📋 Información que necesitas

### 1. **Datos de tu proyecto Google Cloud existente**
- **PROJECT_ID**: ID de tu proyecto actual
- **PROJECT_NUMBER**: Número del proyecto (Dashboard → Configuración del proyecto)
- **REGION**: Región preferida (recomendado: `us-central1`)
- **SERVICE_ACCOUNT**: `cloudrun@storage-entorno-de-desarrollo.iam.gserviceaccount.com` (ya existente)

### 2. **Datos de GitHub**
- **REPOSITORY**: Nombre completo del repositorio (ej: `usuario/caddis-automation`)

### 3. **Datos de Google Sheets**
- **GOOGLE_SHEETS_ID**: ID de tu hoja de cálculo (extraído de la URL)

---

## 🔧 Configuración Rápida

### Paso 1: Habilitar APIs necesarias
```bash
# Configurar tu proyecto existente
gcloud config set project TU_PROJECT_ID

# Habilitar APIs requeridas
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable sheets.googleapis.com
gcloud services enable drive.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
```

### Paso 2: Crear recursos necesarios
```bash
# Variables (reemplaza con tus datos)
export PROJECT_ID="TU_PROJECT_ID"
export PROJECT_NUMBER="TU_PROJECT_NUMBER"  
export REPO="TU_USUARIO/TU_REPOSITORIO"
export SERVICE_ACCOUNT="cloudrun@storage-entorno-de-desarrollo.iam.gserviceaccount.com"

# 1. Crear Artifact Registry
gcloud artifacts repositories create caddis-automation \
  --repository-format=docker \
  --location=us-central1 \
  --description="Repositorio para Caddis Automation"

# 2. Verificar permisos del Service Account existente (opcional)
echo "Verificando permisos del service account existente..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/artifactregistry.admin"

echo "✅ Permisos verificados/agregados al service account existente"
```

### Paso 3: Configurar Workload Identity Federation
```bash
# Crear Workload Identity Pool
gcloud iam workload-identity-pools create github-pool \
  --location="global" \
  --description="Pool para GitHub Actions"

# Crear Provider
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location="global" \
  --workload-identity-pool=github-pool \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='$REPO'"

# Permitir que GitHub Actions use el Service Account
gcloud iam service-accounts add-iam-policy-binding \
  $SERVICE_ACCOUNT \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/$REPO"
```

### Paso 4: Crear Secrets
```bash
# Crear secret con credenciales de Caddis y Google Sheets
gcloud secrets create caddis-secrets \
  --data-file=<(echo '{
    "username": "GPSMUNDO-TEST",
    "password": "875c471f5ad0b48114193d35f3ef45f6",
    "sheets-id": "TU_GOOGLE_SHEETS_ID_AQUI"
  }')
```

---

## 📊 Configurar Google Sheets

### 1. Preparar la hoja de cálculo
1. **Crear nueva hoja** en [Google Sheets](https://sheets.google.com)
2. **Obtener el ID** de la URL: `https://docs.google.com/spreadsheets/d/ESTE_ES_EL_ID/edit`
3. **Compartir la hoja** con: `cloudrun@storage-entorno-de-desarrollo.iam.gserviceaccount.com`
4. **Dar permisos de Editor** al service account

### 2. Actualizar el secret con el ID de la hoja
```bash
# Actualizar secret con el ID real de tu Google Sheets
gcloud secrets versions add caddis-secrets \
  --data-file=<(echo '{
    "username": "GPSMUNDO-TEST",
    "password": "875c471f5ad0b48114193d35f3ef45f6",
    "sheets-id": "TU_GOOGLE_SHEETS_ID_REAL"
  }')
```

---

## 🐙 Configurar GitHub Secrets

En tu repositorio GitHub → Settings → Secrets and variables → Actions

Agrega estos **Repository Secrets**:

```
PROJECT_ID=tu-project-id-real
REGION=us-central1
REPOSITORY=caddis-automation
JOB_NAME=caddis-automation
WIF_PROVIDER=projects/TU_PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/providers/github-provider
WIF_SERVICE_ACCOUNT=cloudrun@storage-entorno-de-desarrollo.iam.gserviceaccount.com
CADDIS_API_URL=https://api.caddis.com.ar
CADDIS_USERNAME=GPSMUNDO-TEST
CADDIS_PASSWORD=875c471f5ad0b48114193d35f3ef45f6
GOOGLE_SHEETS_ID=tu-google-sheets-id-real
```

---

## 🚀 Desplegar

### Opción 1: Despliegue automático (Recomendado)
1. **Hacer push** al repositorio:
   ```bash
   git add .
   git commit -m "Initial deployment"
   git push origin main
   ```
2. **Monitorear** en GitHub Actions tab

### Opción 2: Despliegue manual
```bash
# Usar el script de despliegue incluido
chmod +x deploy.sh
./deploy.sh
```

---

## ⏰ Programar Ejecución desde Google Cloud Console

### Opción A: Cloud Scheduler (Interfaz web)
1. Ve a **Cloud Scheduler** en la consola de Google Cloud
2. Clic en **"Crear Job"**
3. Configurar:
   - **Nombre**: `caddis-automation-scheduler`
   - **Región**: `us-central1`
   - **Frecuencia**: `0 */6 * * *` (cada 6 horas)
   - **Zona horaria**: Tu zona horaria
   - **Tipo de destino**: HTTP
   - **URL**: `https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/TU_PROJECT_ID/jobs/caddis-automation:run`
   - **Método HTTP**: POST
   - **Autenticación**: OAuth token
   - **Service Account**: `cloudrun@storage-entorno-de-desarrollo.iam.gserviceaccount.com`

### Opción B: Cloud Scheduler (CLI)
```bash
gcloud scheduler jobs create http caddis-automation-scheduler \
  --schedule="0 */6 * * *" \
  --uri="https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/caddis-automation:run" \
  --http-method=POST \
  --oauth-service-account-email=cloudrun@storage-entorno-de-desarrollo.iam.gserviceaccount.com \
  --location=us-central1
```

### Horarios de ejemplo:
- **Cada 6 horas**: `0 */6 * * *`
- **Diariamente a las 2 AM**: `0 2 * * *`
- **Cada lunes a las 8 AM**: `0 8 * * 1`
- **Cada hora (9-17h, L-V)**: `0 9-17 * * 1-5`

---

## ✅ Verificar que funciona

### Ejecutar manualmente
```bash
# Ejecutar el job inmediatamente
gcloud run jobs execute caddis-automation --region=us-central1

# Ver logs en tiempo real
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=caddis-automation" --limit=20 --format="table(timestamp,textPayload)"
```

### Verificar en Google Sheets
1. Abre tu hoja de cálculo
2. Deberías ver una hoja llamada **"Caddis Data"** con los datos
3. Verificar que las columnas coinciden con el mapeo esperado

---

## 🔍 Comandos útiles

```bash
# Ver estado del job
gcloud run jobs describe caddis-automation --region=us-central1

# Ver jobs programados
gcloud scheduler jobs list --location=us-central1

# Ejecutar scheduler manualmente
gcloud scheduler jobs run caddis-automation-scheduler --location=us-central1

# Ver contenido de secrets
gcloud secrets versions access latest --secret=caddis-secrets

# Ver logs del scheduler
gcloud logging read "resource.type=cloud_scheduler_job" --limit=10
```

---

## 🆘 Solución de problemas

### ❌ Error de autenticación con Google Sheets
```bash
# Verificar que el service account tiene acceso
gcloud projects get-iam-policy $PROJECT_ID --flatten="bindings[].members" --filter="bindings.members:cloudrun@storage-entorno-de-desarrollo.iam.gserviceaccount.com"
```

### ❌ Error de autenticación con Caddis
- Las credenciales están hardcodeadas en el código: `GPSMUNDO-TEST` / `875c471f5ad0b48114193d35f3ef45f6`
- Verificar que la API de Caddis esté disponible

### ❌ Job no se ejecuta
```bash
# Verificar que el job existe
gcloud run jobs list --region=us-central1

# Verificar scheduler
gcloud scheduler jobs describe caddis-automation-scheduler --location=us-central1
```

### ❌ Error en GitHub Actions
- Verificar que todos los secrets están configurados correctamente
- Verificar que el PROJECT_NUMBER es correcto (no el PROJECT_ID)

---

## 📝 Resumen de lo que necesitas hacer

1. ✅ **Ejecutar comandos** de configuración (Pasos 1-4)
2. ✅ **Configurar Google Sheets** y compartir con service account
3. ✅ **Configurar GitHub Secrets** con tus datos reales
4. ✅ **Hacer push** al repositorio para desplegar
5. ✅ **Configurar Cloud Scheduler** desde la consola de Google Cloud
6. ✅ **Verificar** que todo funciona ejecutando manualmente

¡Listo! El sistema estará funcionando automáticamente según el horario que configures.