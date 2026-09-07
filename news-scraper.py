#!/usr/bin/env python3
"""
Script de scraping de noticias tech en español
Busca en múltiples fuentes y guarda en Google Sheets
"""

import os
import json
import requests
from datetime import datetime, timedelta
from collections import defaultdict
import re
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
import gspread

# Configuración
NEWS_API_KEY = os.environ.get('NEWS_API_KEY')
GOOGLE_CREDENTIALS = os.environ.get('GOOGLE_CREDENTIALS')
SHEET_NAME = "Tech-News-Daily-Joaquín"

# Keywords por categoría
KEYWORDS_BY_CATEGORY = {
    "IA": [
        "inteligencia artificial", "machine learning", "deep learning", 
        "redes neuronales", "LLM", "GPT", "Claude", "transformers",
        "algoritmos de IA", "neural networks", "AI", "artificial intelligence"
    ],
    "Ciencia de Datos": [
        "ciencia de datos", "data science", "análisis de datos", "data analytics",
        "big data", "data engineering", "ingeniería de datos", "ETL",
        "data mining", "minería de datos", "analytics"
    ],
    "Cloud": [
        "cloud computing", "computación en la nube", "AWS", "Google Cloud",
        "Azure", "serverless", "contenedores", "Kubernetes", "DevOps",
        "infraestructura en la nube", "cloud infrastructure"
    ],
    "Tecnología": [
        "software", "desarrollo de software", "programación", "startup",
        "innovación tecnológica", "tecnología", "tech", "software engineering",
        "desarrollo web", "aplicaciones"
    ],
    "Hardware": [
        "GPU", "TPU", "computación cuántica", "quantum computing",
        "chips", "procesador", "hardware", "semiconductor", "transistores",
        "arquitectura de computadoras", "NVIDIA", "Intel"
    ],
    "Innovación": [
        "innovación", "breakthrough", "descubrimiento", "research",
        "investigación", "nuevo producto", "producto", "revolución tecnológica",
        "disruptivo", "disruption"
    ]
}

def get_category(title, description=""):
    """Clasifica una noticia según su contenido"""
    text = (title + " " + description).lower()
    
    for category, keywords in KEYWORDS_BY_CATEGORY.items():
        for keyword in keywords:
            if keyword.lower() in text:
                return category
    
    return "Tecnología"  # Categoría por defecto

def fetch_newsapi_articles():
    """Busca artículos en NewsAPI"""
    articles = []
    
    if not NEWS_API_KEY:
        print("⚠️  NEWS_API_KEY no configurada")
        return articles
    
    try:
        # Búsqueda principal
        query = "inteligencia artificial OR machine learning OR data science OR cloud computing OR innovación tecnológica"
        url = "https://newsapi.org/v2/everything"
        
        params = {
            'q': query,
            'language': 'es',
            'sort_by': 'publishedAt',
            'pageSize': 50,
            'apiKey': NEWS_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if data.get('articles'):
            for article in data['articles']:
                articles.append({
                    'titulo': article.get('title', ''),
                    'descripcion': article.get('description', ''),
                    'url': article.get('url', ''),
                    'fuente': article.get('source', {}).get('name', 'NewsAPI'),
                    'fecha_publicacion': article.get('publishedAt', ''),
                    'imagen': article.get('urlToImage', '')
                })
        
        print(f"✅ NewsAPI: {len(articles)} artículos encontrados")
    except Exception as e:
        print(f"❌ Error en NewsAPI: {e}")
    
    return articles

def fetch_hackernews_articles():
    """Busca en HackerNews (Top stories)"""
    articles = []
    
    try:
        # Obtener top stories
        url = "https://hacker-news.firebaseio.com/v0/topstories.json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        story_ids = response.json()[:30]  # Top 30
        
        keywords_hn = ["AI", "machine learning", "data", "cloud", "tech", "innovation"]
        
        for story_id in story_ids:
            try:
                story_url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
                story = requests.get(story_url, timeout=5).json()
                
                title = story.get('title', '')
                # Filtrar por relevancia
                if any(kw.lower() in title.lower() for kw in keywords_hn):
                    articles.append({
                        'titulo': title,
                        'descripcion': '',
                        'url': story.get('url', f"https://news.ycombinator.com/item?id={story_id}"),
                        'fuente': 'HackerNews',
                        'fecha_publicacion': datetime.now().isoformat(),
                        'imagen': ''
                    })
            except:
                continue
        
        print(f"✅ HackerNews: {len(articles)} artículos encontrados")
    except Exception as e:
        print(f"❌ Error en HackerNews: {e}")
    
    return articles

def fetch_arxiv_recent():
    """Busca papers recientes en ArXiv (IA/ML)"""
    articles = []
    
    try:
        # ArXiv papers de últimas 24 horas en categorías de IA
        categories = ['cs.AI', 'cs.LG', 'stat.ML']
        
        for cat in categories:
            url = f"http://export.arxiv.org/api/query?search_query=cat:{cat}&start=0&max_results=20&sortBy=submittedDate&sortOrder=descending"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # Parse XML
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.content)
            
            for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
                title = entry.find('{http://www.w3.org/2005/Atom}title').text
                summary = entry.find('{http://www.w3.org/2005/Atom}summary').text
                arxiv_id = entry.find('{http://www.w3.org/2005/Atom}id').text.split('/abs/')[-1]
                
                articles.append({
                    'titulo': title.strip(),
                    'descripcion': summary.strip()[:200],
                    'url': f"https://arxiv.org/abs/{arxiv_id}",
                    'fuente': 'ArXiv',
                    'fecha_publicacion': datetime.now().isoformat(),
                    'imagen': ''
                })
        
        print(f"✅ ArXiv: {len(articles)} papers encontrados")
    except Exception as e:
        print(f"❌ Error en ArXiv: {e}")
    
    return articles

def remove_duplicates(articles):
    """Elimina noticias duplicadas"""
    seen = {}
    unique = []
    
    for article in articles:
        # Normalizar título
        title_normalized = article['titulo'].lower().strip()
        
        # Buscar similitud simple
        is_duplicate = False
        for seen_title in seen:
            if title_normalized == seen_title or title_normalized in seen_title or seen_title in title_normalized:
                is_duplicate = True
                break
        
        if not is_duplicate:
            seen[title_normalized] = True
            unique.append(article)
    
    return unique

def save_to_google_sheets(articles):
    """Guarda artículos en Google Sheets"""
    try:
        # Autenticar con Google
        creds_dict = json.loads(GOOGLE_CREDENTIALS)
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        )
        client = gspread.authorize(creds)
        
        # Abrir o crear sheet
        try:
            sheet = client.open(SHEET_NAME).sheet1
        except:
            # Si no existe, crear nuevo
            spreadsheet = client.create(SHEET_NAME)
            sheet = spreadsheet.sheet1
            # Agregar headers
            headers = ["Fecha Scrape", "Fecha Pub", "Categoría", "Título", "Descripción", "Fuente", "URL", "Importancia"]
            sheet.append_row(headers)
        
        # Agregar artículos
        today = datetime.now().strftime("%Y-%m-%d")
        
        for article in articles[:15]:  # Top 15
            categoria = get_category(article['titulo'], article['descripcion'])
            row = [
                today,
                article['fecha_publicacion'][:10],
                categoria,
                article['titulo'][:100],
                article['descripcion'][:100],
                article['fuente'],
                article['url'],
                ""  # Importancia (vacío para que lo llenes después)
            ]
            sheet.append_row(row)
        
        print(f"✅ {len(articles[:15])} artículos guardados en Google Sheets")
        return True
    except Exception as e:
        print(f"❌ Error guardando en Google Sheets: {e}")
        return False

def main():
    """Función principal"""
    print(f"🚀 Iniciando scraping de noticias - {datetime.now()}")
    
    all_articles = []
    
    # Buscar en todas las fuentes
    all_articles.extend(fetch_newsapi_articles())
    all_articles.extend(fetch_hackernews_articles())
    all_articles.extend(fetch_arxiv_recent())
    
    print(f"📊 Total de artículos antes de filtrar: {len(all_articles)}")
    
    # Eliminar duplicados
    unique_articles = remove_duplicates(all_articles)
    print(f"🔍 Artículos únicos: {len(unique_articles)}")
    
    # Ordenar por relevancia (aquí puedes agregar lógica más sofisticada)
    # Por ahora, los primeros son los más recientes
    
    # Guardar en Google Sheets
    success = save_to_google_sheets(unique_articles)
    
    if success:
        print("✅ ¡Proceso completado exitosamente!")
    else:
        print("❌ Hubo errores en el proceso")

if __name__ == "__main__":
    main()
