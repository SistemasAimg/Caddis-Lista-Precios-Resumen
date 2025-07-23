#!/usr/bin/env python3
"""
Caddis API Data Extraction and Google Sheets Upload Script

This script authenticates with Google Cloud using Workload Identity Federation,
extracts data from Caddis API endpoints, processes and combines the data,
and uploads it to a Google Sheets spreadsheet.

Author: DevOps Automation Team
"""

import os
import sys
import json
import logging
import requests
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
import yaml

import gspread
from google.auth import default
from google.auth.transport.requests import Request

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class CaddisAPIClient:
    """Client for interacting with Caddis API"""
    
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        self.token = None
        
        # Authenticate and get token
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Caddis API and get access token"""
        try:
            login_url = f"{self.base_url}/v1/login"
            login_data = {
                "usuario": self.username,
                "password": self.password
            }

            logger.info("Authenticating with Caddis API...")
            response = self.session.post(login_url, json=login_data, timeout=30)
            response.raise_for_status()

            auth_response = response.json()

            # Possible locations of the token in the API response
            if 'token' in auth_response:
                self.token = auth_response['token']
            elif 'access_token' in auth_response:
                self.token = auth_response['access_token']
            elif 'body' in auth_response:
                # Token may be nested inside "body"
                if 'token' in auth_response['body']:
                    self.token = auth_response['body']['token']
                elif 'access_token' in auth_response['body']:
                    self.token = auth_response['body']['access_token']

            # Validate that we actually found a token
            if not self.token:
                logger.error(f"Unexpected authentication response structure: {auth_response}")
                raise ValueError("Could not find token in authentication response")

            # Update session headers with the token
            self.session.headers.update({
                'Authorization': f'Bearer {self.token}'
            })

            logger.info("Successfully authenticated with Caddis API")

        except requests.exceptions.RequestException as e:
            logger.error(f"Authentication failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            raise
    
    def get_articles(self) -> List[Dict[str, Any]]:
        """
        Fetch all articles from /v1/articulos endpoint
        Iterates through all pages until body array is empty
        """
        articles = []
        page = 1
        
        logger.info("Starting articles extraction...")
        
        while True:
            try:
                url = f"{self.base_url}/v1/articulos?pagina={page}"
                logger.info(f"Fetching articles page {page}")
                
                response = self.session.get(url, timeout=30)
                
                # Si es 404, significa que no hay más páginas
                if response.status_code == 404:
                    logger.info(f"No more articles found at page {page} (404 response)")
                    break
                
                response.raise_for_status()
                
                data = response.json()
                
                # Para /v1/articulos, body es un array directo
                body_data = data.get('body', [])
                if isinstance(body_data, list):
                    articles_data = body_data
                else:
                    articles_data = []
                
                if not articles_data:
                    logger.info(f"No more articles found at page {page}")
                    break
                
                # Extract required fields for each article
                for article in articles_data:
                    # Skip inactive SKUs
                    if str(article.get('estado', '')).upper() == 'INACTIVO':
                        continue
                    article_data = {
                        'id': article.get('id'),
                        'sku': article.get('sku'),
                        'nombre': article.get('nombre'),
                        'tipo': article.get('tipo'),
                        'marca': article.get('marca'),
                        'grupo': article.get('grupo')
                    }
                    articles.append(article_data)
                
                logger.info(f"Extracted {len(articles_data)} articles from page {page}")
                page += 1
                
                # Rate limiting
                time.sleep(0.5)  # Aumentado para evitar 503 errors
                
            except requests.exceptions.RequestException as e:
                # Si es un error 404, ya lo manejamos arriba
                if hasattr(e, 'response') and e.response.status_code == 404:
                    logger.info(f"No more articles found at page {page} (404 response)")
                    break
                else:
                    logger.error(f"Error fetching articles page {page}: {str(e)}")
                    raise
        
        logger.info(f"Total articles extracted: {len(articles)}")
        return articles
    
    def get_prices(self, price_lists: List[int]) -> List[Dict[str, Any]]:
        """
        Fetch all prices from /v1/articulos/precios endpoint
        Iterates through all pages and all price lists
        """
        prices = []
        
        logger.info("Starting prices extraction...")
        
        for lista_id in price_lists:
            logger.info(f"Processing price list {lista_id}")
            
            # Iterate through pages until we get a 404 or empty response
            page = 1
            while True:
                try:
                    url = f"{self.base_url}/v1/articulos/precios?pagina={page}&lista={lista_id}&mostrar_sin_precio=true"
                    logger.info(f"Fetching prices for list {lista_id}, page {page}")
                    
                    response = self.session.get(url, timeout=30)
                    
                    # Si es 404, significa que no hay más páginas para esta lista
                    if response.status_code == 404:
                        logger.info(f"No more pages for price list {lista_id} at page {page} (404 response)")
                        break
                    
                    response.raise_for_status()
                    
                    data = response.json()
                    
                    # Para /v1/articulos/precios, body es un objeto con articulos dentro
                    body_data = data.get('body', {})
                    if isinstance(body_data, dict):
                        prices_data = body_data.get('articulos', [])
                    else:
                        prices_data = []
                    
                    # Si no hay datos en el body, terminamos con esta lista
                    if not prices_data:
                        logger.info(f"No more data for price list {lista_id} at page {page}")
                        break
                    
                    # Extract required fields for each price entry
                    for price_item_dict in prices_data:
                        # Calcula precio con IVA incluido
                        try:
                            precio_base = float(price_item_dict.get('precio_unitario', 0))
                            iva_rate    = float(price_item_dict.get('iva_tasa', 0))  # ej. 0.105
                        except (TypeError, ValueError):
                            logger.warning(f"Precio o IVA no numérico para SKU {price_item_dict.get('sku')}")
                            continue

                        precio_con_iva = round(precio_base * (1 + iva_rate), 2)

                        price_data = {
                            'sku'            : price_item_dict.get('sku'),
                            'lista_id'       : lista_id,
                            'iva_tasa'       : iva_rate,           # guardamos como 0.105
                            'precio_unitario': precio_con_iva      # ya incluye IVA
                        }
                        prices.append(price_data)
                    
                    logger.info(f"Extracted {len(prices_data)} prices from list {lista_id}, page {page}")
                    page += 1
                    
                    # Rate limiting
                    time.sleep(0.5)  # Aumentado para evitar 503 errors
                    
                except requests.exceptions.RequestException as e:
                    # Si es un error 404, ya lo manejamos arriba
                    if hasattr(e, 'response') and e.response.status_code == 404:
                        logger.info(f"No more pages for price list {lista_id} at page {page} (404 response)")
                        break
                    else:
                        logger.error(f"Error fetching prices for list {lista_id}, page {page}: {str(e)}")
                        # Para otros errores, continuamos con la siguiente lista en lugar de fallar completamente
                        logger.warning(f"Skipping remaining pages for price list {lista_id} due to error")
                        break
        
        logger.info(f"Total price entries extracted: {len(prices)}")
        return prices

class GoogleSheetsClient:
    """Client for interacting with Google Sheets"""
    
    def __init__(self, spreadsheet_id: str):
        self.spreadsheet_id = spreadsheet_id
        self.client = self._authenticate()
        self.spreadsheet = self.client.open_by_key(spreadsheet_id)
    
    def _authenticate(self):
        """Authenticate with Google Sheets using Workload Identity Federation"""
        try:
            # Try to use default credentials (Workload Identity Federation)
            credentials, project = default(scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ])
            
            logger.info("Successfully authenticated with Google Cloud using Workload Identity Federation")
            return gspread.authorize(credentials)
            
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Cloud: {str(e)}")
            raise
    
    def update_sheet(self, data: List[List[Any]], sheet_name: str = "Caddis Data"):
        """Update or create a sheet with the provided data"""
        try:
            # Try to get existing worksheet
            try:
                worksheet = self.spreadsheet.worksheet(sheet_name)
                logger.info(f"Found existing worksheet: {sheet_name}")
            except gspread.WorksheetNotFound:
                # Create new worksheet
                worksheet = self.spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=30)
                logger.info(f"Created new worksheet: {sheet_name}")
            
            # Clear existing data
            worksheet.clear()
            
            # Update with new data
            if data:
                worksheet.update('A1', data)
                logger.info(f"Updated {len(data)} rows in worksheet {sheet_name}")
                # Apply number/text formats
                try:
                    # Column A (SKU) as plain text
                    worksheet.format('A:A', {
                        "numberFormat": {"type": "TEXT"}
                    })
                    # Columns G to AD (price lists) as number with two decimals
                    worksheet.format('G:AD', {
                        "numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"}
                    })
                    logger.info("Applied column formats (SKU as text, prices as number)")
                except Exception as fmt_err:
                    logger.warning(f"Could not apply formats: {fmt_err}")
            
        except Exception as e:
            logger.error(f"Error updating Google Sheet: {str(e)}")
            raise

class DataProcessor:
    """Process and combine data from articles and prices"""
    
    # Price list mapping to column names
    PRICE_LIST_MAPPING = {
        1: "Minorista Ars",
        2: "Dealer Ars", 
        3: "Dealer 1 Ars",
        5: "Dealer 30d Ars",
        7: "Nautica Dealer Usd",
        8: "Dealer 60d Ars",
        9: "Mino Ml Premium Ars",
        10: "Sub Distribuidor Usd",
        11: "Dealer 55mkup Ars",
        12: "Dealer 50mkup Ars",
        13: "Anterior Mino Ars",
        14: "Mixta Ars",
        15: "Grouping 70mkup Ars",
        16: "Dealer Cencosud Ars",
        17: "Nautica Dealer 1 Usd",
        18: "Nautica Dealer Ars",
        19: "Nautica Dealer 1 Ars",
        20: "Fob Standard Usd",
        21: "Dealer Golf Ars",
        22: "Gpsmundo Srl",
        23: "Dealer Meli Ars",
        24: "Dealer 5g Ars",
        25: "Fob Supplier Llc",
        33: "Dealer Diggit Ars"
    }
    
    @classmethod
    def combine_data(cls, articles: List[Dict], prices: List[Dict]) -> List[List[Any]]:
        """Combine articles and prices data into final format"""
        logger.info("Starting data combination process...")
        
        # Create articles lookup by SKU
        articles_lookup = {article['sku']: article for article in articles if article.get('sku')}
        
        # Create prices lookup by SKU and lista_id
        prices_lookup = {}
        for price in prices:
            sku = price.get('sku')
            lista_id = price.get('lista_id')
            if sku and lista_id:
                if sku not in prices_lookup:
                    prices_lookup[sku] = {}
                prices_lookup[sku][lista_id] = price
        
        # Prepare header row
        header = [
            "Código", "Tipo", "Artículo", "Grupo", "Marca", "IVA",
            "Minorista Ars", "Dealer Ars", "Dealer 1 Ars", "Dealer 30d Ars",
            "Nautica Dealer Usd", "Dealer 60d Ars", "Mino Ml Premium Ars",
            "Sub Distribuidor Usd", "Dealer 55mkup Ars", "Dealer 50mkup Ars",
            "Anterior Mino Ars", "Mixta Ars", "Grouping 70mkup Ars",
            "Dealer Cencosud Ars", "Nautica Dealer 1 Usd", "Nautica Dealer Ars",
            "Nautica Dealer 1 Ars", "Fob Standard Usd", "Dealer Golf Ars",
            "Gpsmundo Srl", "Dealer Meli Ars", "Dealer 5g Ars",
            "Fob Supplier Llc", "Dealer Diggit Ars"
        ]
        
        # Process all unique SKUs (only those from articles, i.e., active SKUs)
        all_skus = set(articles_lookup.keys())
        result_data = [header]
        
        for sku in sorted(all_skus):
            article = articles_lookup.get(sku, {})
            sku_prices = prices_lookup.get(sku, {})

            # IVA (tomamos el de la lista 1 si existe)
            iva_rate = sku_prices.get(1, {}).get('iva_tasa', '')
            if iva_rate != '':
                iva_percent = round(float(iva_rate) * 100, 1)       # 0.105 -> 10.5
                iva_display = str(iva_percent).replace('.', ',')    # "10,5"
            else:
                iva_display = ''

            row = [
                sku,                                # Código
                article.get('tipo', ''),            # Tipo
                article.get('nombre', ''),          # Artículo
                article.get('grupo', ''),           # Grupo
                article.get('marca', ''),           # Marca
                iva_display                         # IVA %
            ]

            # Add prices for each column
            for lista_id in [1, 2, 3, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 33]:
                price_info = sku_prices.get(lista_id, {})
                precio_unitario = price_info.get('precio_unitario', '')
                if precio_unitario != '':
                    try:
                        row.append(round(float(precio_unitario), 2))   # número plano
                    except ValueError:
                        row.append('')  # si falla la conversión mantenemos vacío
                else:
                    row.append('')

            result_data.append(row)
        
        logger.info(f"Combined data for {len(result_data)-1} products")
        return result_data

def load_config() -> Dict[str, Any]:
    """Load configuration from config.yaml or environment variables"""
    config = {}
    
    # Try to load from config.yaml
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        logger.info("Configuration loaded from config.yaml")
    except FileNotFoundError:
        logger.info("config.yaml not found, using environment variables")
    except Exception as e:
        logger.warning(f"Error loading config.yaml: {e}, using environment variables")
        config = {}
    
    # Override with environment variables
    # Override with environment variables (only if they exist)
    if os.getenv('CADDIS_API_URL'):
        config['caddis_api_url'] = os.getenv('CADDIS_API_URL')
    if os.getenv('CADDIS_USERNAME'):
        config['caddis_username'] = os.getenv('CADDIS_USERNAME')
    if os.getenv('CADDIS_PASSWORD'):
        config['caddis_password'] = os.getenv('CADDIS_PASSWORD')
    if os.getenv('GOOGLE_SHEETS_ID'):
        config['google_sheets_id'] = os.getenv('GOOGLE_SHEETS_ID')
    if os.getenv('PRICE_LISTS'):
        price_lists_str = os.getenv('PRICE_LISTS', '1,2,3,5,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,33')
        config['price_lists'] = [int(x.strip()) for x in price_lists_str.split(',') if x.strip().isdigit()]
    
    # Ensure price_lists is set if not already configured
    if 'price_lists' not in config or not config['price_lists']:
        config['price_lists'] = [1, 2, 3, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 33]
    
    logger.info(f"Final configuration: caddis_api_url={config.get('caddis_api_url', 'NOT_SET')}, "
                f"google_sheets_id={'SET' if config.get('google_sheets_id') else 'NOT_SET'}, "
                f"price_lists_count={len(config.get('price_lists', []))}")
    
    return config

def main():
    """Main execution function"""
    logger.info("Starting Caddis API data extraction and Google Sheets upload process")
    
    try:
        # Load configuration
        config = load_config()
        
        # Validate required configuration
        required_configs = ['caddis_api_url', 'caddis_username', 'caddis_password', 'google_sheets_id']
        for req_config in required_configs:
            if not config.get(req_config):
                raise ValueError(f"Missing required configuration: {req_config}")
        
        # Initialize clients
        caddis_client = CaddisAPIClient(
            base_url=config['caddis_api_url'],
            username=config['caddis_username'],
            password=config['caddis_password']
        )
        
        sheets_client = GoogleSheetsClient(
            spreadsheet_id=config['google_sheets_id']
        )
        
        # Extract data
        logger.info("Phase 1: Extracting articles...")
        articles = caddis_client.get_articles()
        
        logger.info("Phase 2: Extracting prices...")
        price_lists = config.get('price_lists', [1, 2, 3, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 33])
        prices = caddis_client.get_prices(price_lists)
        
        # Process and combine data
        logger.info("Phase 3: Processing and combining data...")
        combined_data = DataProcessor.combine_data(articles, prices)
        
        # Upload to Google Sheets
        logger.info("Phase 4: Uploading to Google Sheets...")
        sheets_client.update_sheet(combined_data)
        
        logger.info("Process completed successfully!")
        
    except Exception as e:
        logger.error(f"Process failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()