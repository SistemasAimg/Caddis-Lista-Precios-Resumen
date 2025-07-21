#!/bin/bash

# Deployment script for Caddis Automation
# This script sets up the necessary GCP resources and deploys the Cloud Run Job

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID=${PROJECT_ID:-""}
REGION=${REGION:-"us-central1"}
REPOSITORY=${REPOSITORY:-"caddis-automation"}
JOB_NAME=${JOB_NAME:-"caddis-automation"}
SERVICE_ACCOUNT_NAME="caddis-automation-sa"
SECRET_NAME="caddis-secrets"

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_dependencies() {
    log_info "Checking dependencies..."
    
    if ! command -v gcloud &> /dev/null; then
        log_error "gcloud CLI not found. Please install Google Cloud SDK."
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker not found. Please install Docker."
        exit 1
    fi
    
    log_info "Dependencies check passed."
}

setup_project() {
    log_info "Setting up GCP project..."
    
    if [ -z "$PROJECT_ID" ]; then
        # Try to get current project if not set
        PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
        if [ -z "$PROJECT_ID" ]; then
            log_error "PROJECT_ID environment variable is required or set current project with: gcloud config set project YOUR_PROJECT_ID"
            exit 1
        fi
        log_info "Using current project: $PROJECT_ID"
    fi
    
    # Ensure we're using the correct project
    gcloud config set project $PROJECT_ID
    
    # Enable required APIs
    log_info "Enabling required APIs..."
    gcloud services enable run.googleapis.com
    gcloud services enable artifactregistry.googleapis.com
    gcloud services enable sheets.googleapis.com
    gcloud services enable drive.googleapis.com
    
    log_info "APIs enabled successfully."
}

check_existing_resources() {
    log_info "Checking existing resources..."
    
    # Check if Artifact Registry exists
    if gcloud artifacts repositories describe $REPOSITORY --location=$REGION &> /dev/null; then
        log_info "✅ Artifact Registry repository already exists"
    else
        log_warning "❌ Artifact Registry repository does not exist - will create"
    fi
    
    # Check if service account exists
    if gcloud iam service-accounts describe $SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com &> /dev/null; then
        log_info "✅ Service account already exists"
    else
        log_warning "❌ Service account does not exist - will create"
    fi
    
    # Check if secrets exist
    if gcloud secrets describe $SECRET_NAME &> /dev/null; then
        log_info "✅ Secrets already exist"
    else
        log_warning "❌ Secrets do not exist - will create"
    fi
}

create_artifact_registry() {
    log_info "Creating Artifact Registry repository..."
    
    # Check if repository exists
    if gcloud artifacts repositories describe $REPOSITORY --location=$REGION &> /dev/null; then
        log_warning "Artifact Registry repository already exists."
    else
        gcloud artifacts repositories create $REPOSITORY \
            --repository-format=docker \
            --location=$REGION \
            --description="Caddis Automation Docker Images"
        log_info "Artifact Registry repository created."
    fi
}

create_service_account() {
    log_info "Creating service account..."
    
    # Check if service account exists
    if gcloud iam service-accounts describe $SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com &> /dev/null; then
        log_warning "Service account already exists."
    else
        gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
            --display-name="Caddis Automation Service Account" \
            --description="Service account for Caddis API automation"
        log_info "Service account created."
    fi
    
    # Grant necessary permissions
    log_info "Granting permissions to service account..."
    
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
        --role="roles/run.invoker"
    
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
        --role="roles/secretmanager.secretAccessor"
    
    log_info "Permissions granted."
}

create_secrets() {
    log_info "Creating secrets..."
    
    # Create secret if it doesn't exist
    if gcloud secrets describe $SECRET_NAME &> /dev/null; then
        log_warning "Secret already exists."
    else
        gcloud secrets create $SECRET_NAME \
            --data-file=- <<< "{}"
        log_info "Secret created."
    fi
    
    log_info "Please update secrets using:"
    log_info "gcloud secrets versions add $SECRET_NAME --data-file=<(echo '{\"username\":\"GPSMUNDO-TEST\",\"password\":\"875c471f5ad0b48114193d35f3ef45f6\",\"sheets-id\":\"YOUR_SHEETS_ID\"}')"
    log_info ""
    log_info "Replace YOUR_SHEETS_ID with your actual Google Sheets ID"
}

build_and_push_image() {
    log_info "Building and pushing Docker image..."
    
    # Configure Docker
    gcloud auth configure-docker $REGION-docker.pkg.dev
    
    # Build image
    docker build -t $REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/caddis-automation:latest .
    
    # Push image
    docker push $REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/caddis-automation:latest
    
    log_info "Docker image built and pushed successfully."
}

deploy_job() {
    log_info "Deploying Cloud Run Job..."
    
    # Remove schedule.yaml if it exists (cleanup from previous versions)
    if [ -f "schedule.yaml" ]; then
        rm schedule.yaml
        log_info "Removed old schedule.yaml file"
    fi
    
    # Replace placeholders in job.yaml
    sed -e "s/PROJECT_ID/$PROJECT_ID/g" \
        -e "s/REGION/$REGION/g" \
        -e "s/REPOSITORY/$REPOSITORY/g" \
        -e "s/CADDIS_API_URL_PLACEHOLDER/$CADDIS_API_URL/g" \
        job.yaml > job-deployed.yaml
    
    # Deploy job
    gcloud run jobs replace job-deployed.yaml \
        --region=$REGION
    
    # Clean up
    rm job-deployed.yaml
    
    log_info "Cloud Run Job deployed successfully."
}

main() {
    log_info "Starting Caddis Automation deployment..."
    
    check_dependencies
    check_existing_resources
    setup_project
    create_artifact_registry
    create_service_account
    create_secrets
    build_and_push_image
    deploy_job
    
    log_info "Deployment completed successfully!"
    log_info "To run the job manually:"
    log_info "gcloud run jobs execute $JOB_NAME --region=$REGION"
    log_info ""
    log_info "To set up Cloud Scheduler, follow the instructions in SETUP_GUIDE.md"
}

# Execute main function
main "$@"