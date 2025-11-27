from flask import Flask, request, jsonify, send_from_directory, send_file, make_response, redirect
from flask_cors import CORS, cross_origin
from PIL import Image
import requests
from io import BytesIO, StringIO
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
import os
import logging
import sys
import pytesseract
from werkzeug.serving import WSGIRequestHandler
import tempfile
from datetime import datetime
import subprocess
import json
from pathlib import Path
from dotenv import load_dotenv
from gemini.inputAnalisistxt import analyze_contrast_texts_from_file

load_dotenv()

# Configure logging early so it's available everywhere
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure CORS
cors = CORS()

def create_app():
    app = Flask(__name__)
    cors.init_app(app)
    return app

app = create_app()

# Configure CORS to allow all origins
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Configure Tesseract path (update this to your Tesseract installation path)
if sys.platform == 'win32':
    # Common Tesseract installation paths on Windows
    tesseract_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    ]
    for path in tesseract_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            break
    else:
        print("Warning: Tesseract not found in common locations. Please ensure it's installed and in your PATH.")
else:
    # Default path for Linux containers
    linux_tesseract = os.environ.get('TESSERACT_PATH', '/usr/bin/tesseract')
    if os.path.exists(linux_tesseract):
        pytesseract.pytesseract.tesseract_cmd = linux_tesseract
    else:
        logger.warning(f"Tesseract not found at {linux_tesseract}. OCR may fail until it's installed.")

# Create temp directory if it doesn't exist
base_dir = os.path.dirname(os.path.abspath(__file__))
temp_dir = os.path.join(base_dir, 'temp')
os.makedirs(temp_dir, exist_ok=True)

ALLOWED_THUMBNAIL_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}

# External scraper configuration for the carousel (served by instagram_service.py)
INSTAGRAM_SERVICE_URL = os.environ.get('INSTAGRAM_SERVICE_URL', 'http://localhost:5001')
INSTAGRAM_API_URL = os.environ.get('INSTAGRAM_API_URL')  # legacy direct access
INSTAGRAM_API_KEY = os.environ.get('INSTAGRAM_API_KEY')  # legacy direct access
INSTAGRAM_DEFAULT_USERNAME = os.environ.get('INSTAGRAM_DEFAULT_USERNAME', 'instagram')
DEFAULT_THUMBNAIL_LIMIT = int(os.environ.get('THUMBNAIL_LIMIT', '12'))

# Path for the text file to store all extracted text (used by Gemini)
text_file_path = os.path.join(base_dir, 'gemini', 'extracted_texts.txt')
# Path for the latest analysis output
analysis_output_path = os.path.join(base_dir, 'gemini', 'output_analisis.txt')
# Path for persisted model analysis output
analysis_output_path = os.path.join(base_dir, 'gemini', 'output_analisis.txt')

# Ensure the text file exists
try:
    os.makedirs(os.path.dirname(text_file_path), exist_ok=True)
    if not os.path.exists(text_file_path):
        with open(text_file_path, 'w', encoding='utf-8') as f:
            f.write('Archivo de textos extraídos\n' + '=' * 30 + '\n\n')
except Exception as e:
    logger.error(f'Error creating text file: {str(e)}')

def save_extracted_text(text: str):
    """Append extracted text to the text file with a timestamp"""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(text_file_path, 'a', encoding='utf-8') as f:
            f.write(f'\n\n--- {timestamp} ---\n')
            f.write(text.strip())
            f.write('\n' + '='*50 + '\n')  # Add separator between entries
    except Exception as e:
        logger.error(f'Error saving extracted text: {str(e)}')
        raise


def _instagram_service_base():
    return INSTAGRAM_SERVICE_URL.rstrip('/')


def fetch_remote_thumbnails(username=None, limit=None):
    """
    Pull thumbnails using the dedicated instagram_service.py.
    If the service call fails, tries a legacy direct fetch (INSTAGRAM_API_URL/API_KEY).
    """
    service_url = _instagram_service_base()
    payload = {"username_or_url": (username or '').strip() or INSTAGRAM_DEFAULT_USERNAME}

    # Request instagram_service to fetch/update thumbnails
    try:
        resp = requests.post(f"{service_url}/api/fetch-thumbnails", json=payload, timeout=20)
        resp.raise_for_status()
        logger.info("Thumbnails refreshed via instagram_service.")
    except Exception as exc:
        logger.warning(f'instagram_service fetch failed ({exc}), attempting legacy direct fetch if configured.')
        if not (INSTAGRAM_API_URL and INSTAGRAM_API_KEY):
            return []
        try:
            params = {'api_key': INSTAGRAM_API_KEY}
            user_to_use = payload["username_or_url"] or INSTAGRAM_DEFAULT_USERNAME
            if user_to_use:
                params['username'] = user_to_use
            if limit:
                params['limit'] = limit
            legacy_resp = requests.get(INSTAGRAM_API_URL, params=params, timeout=25)
            legacy_resp.raise_for_status()
        except Exception as legacy_exc:
            logger.error(f'Legacy scraper fetch failed: {legacy_exc}', exc_info=True)
            return []

    # Always list thumbnails from instagram_service
    try:
        list_resp = requests.get(f"{service_url}/api/thumbnails", timeout=10)
        list_resp.raise_for_status()
        data = list_resp.json()
        if isinstance(data, list):
            return data
    except Exception as exc:
        logger.warning(f'Could not list thumbnails from instagram_service: {exc}')
    return []

# CORS is already configured above

# Log all requests
@app.before_request
def log_request_info():
    if request.path != '/':  # Skip logging for static files unless needed
        logger.info(f'Request: {request.method} {request.path}')
        logger.info(f'Headers: {dict(request.headers)}')
        if request.get_data():
            logger.info(f'Body: {request.get_data().decode()}')

@app.after_request
def after_request(response):
    # Skip logging for static files
    if request.path.startswith('/static/'):
        return response
        
    # Log response status and data if it's JSON
    response_data = None
    try:
        if response.is_json:
            response_data = response.get_json()
    except:
        pass
        
    if response_data:
        logger.info(f'Response: {response.status} {response_data}')
    else:
        logger.info(f'Response: {response.status} [Non-JSON response]')
        
    return response

def obtener_imagen_instagram(url):
    # Configurar Selenium
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Configurar el navegador para parecer más real
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        # Abrir la URL
        driver.get(url)
        
        # Esperar a que la página cargue completamente
        time.sleep(5)
        
        # Intentar diferentes selectores comunes de Instagram
        selectores = [
            "//img[contains(@alt, 'Photo by')]",  # Selector por atributo alt
            "//div[contains(@class, 'x5yr21d')]//img",  # Selector por clase contenedora
            "//div[contains(@class, '_aagv')]//img",  # Clase común para imágenes
            "//article//img",  # Último recurso: cualquier imagen dentro de un artículo
            "//img[contains(@src, 'scontent.cdninstagram.com')]"  # Selector por dominio de la imagen
        ]
        
        img_element = None
        for selector in selectores:
            try:
                elements = driver.find_elements("xpath", selector)
                for element in elements:
                    src = element.get_attribute('src')
                    if src and 'http' in src:
                        img_element = element
                        break
                if img_element:
                    break
            except:
                continue
        
        if not img_element:
            # Tomar captura de pantalla para depuración
            driver.save_screenshot('debug_screenshot.png')
            print("Se ha guardado una captura de pantalla para depuración: debug_screenshot.png")
            raise Exception("No se pudo encontrar ningún elemento de imagen con los selectores conocidos")
        
        img_url = img_element.get_attribute('src')
        if not img_url:
            raise Exception("La URL de la imagen está vacía")
            
        # Descargar imagen
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(img_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        img = Image.open(BytesIO(response.content))
        logger.info(f'Imagen descargada - Dimensiones originales: {img.width}x{img.height}')
        return img

    except Exception as e:
        print(f"Error al obtener la imagen: {str(e)}")
        return None
    finally:
        driver.quit()

@app.route('/extract-image', methods=['POST'])
def extract_image():
    logger.info('[/extract-image] Trigger recibido desde frontend')
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'URL no proporcionada'}), 400
    
    try:
        img = obtener_imagen_instagram(data['url'])
        if img:
            # Create a temporary file while preserving original image quality
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg', dir=temp_dir) as temp_file:
                # Save with maximum quality (100) and original dimensions
                img.save(temp_file, 'JPEG', quality=100, optimize=True, progressive=True)
                temp_filename = os.path.basename(temp_file.name)
            
            image_url = f'http://{request.host}/download/{temp_filename}'
            logger.info(f'Imagen guardada con dimensiones originales: {img.width}x{img.height}')
            
            # Extract text using pytesseract
            try:
                # Convert image to RGB if it's not
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Extract text in Spanish and English
                text = pytesseract.image_to_string(img, lang='spa+eng')
                
                if text and text.strip():
                    logger.info(f'Successfully extracted text: {text[:100]}...')  # Log first 100 chars
                    save_extracted_text(text)
                else:
                    logger.info('No text was extracted from the image')
            except Exception as e:
                logger.error(f'Error extracting text: {str(e)}', exc_info=True)
                # Continue even if text extraction fails - we still want to return the image
            
            return jsonify({
                'success': True,
                'image_url': image_url
            })
        else:
            return jsonify({'error': 'No se pudo extraer la imagen'}), 500
    except Exception as e:
        logger.error(f'Error processing image: {str(e)}', exc_info=True)
        return jsonify({'error': f'Error al procesar la imagen: {str(e)}'}), 500

# Route to serve downloaded images
@app.route('/download/<filename>')
def download_file(filename):
    try:
        file_path = os.path.join(temp_dir, filename)
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='image/jpeg')
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        logger.error(f'Error serving file {filename}: {str(e)}')
        return jsonify({'error': 'Error serving file'}), 500

@app.route('/api/thumbnails', methods=['GET'])
def list_thumbnails():
    try:
        # Get list of files from temp directory
        files = []
        for filename in os.listdir(temp_dir):
            if any(filename.lower().endswith(ext) for ext in ALLOWED_THUMBNAIL_EXTENSIONS):
                file_path = os.path.join(temp_dir, filename)
                if os.path.isfile(file_path):
                    mtime = os.path.getmtime(file_path)
                    files.append({
                        'filename': filename,
                        'mtime': mtime
                    })
        
        # Sort by modification time (newest first)
        files.sort(key=lambda x: x['mtime'], reverse=True)
        
        # Apply limit if specified
        limit = request.args.get('limit')
        if limit:
            try:
                limit = int(limit)
                files = files[:limit]
            except ValueError:
                pass
        
        # Return just the filenames for compatibility
        result = [file_info['filename'] for file_info in files]
        
        return jsonify(result)
        return jsonify(data)
    except Exception as e:
        logger.error(f'Error listing thumbnails: {str(e)}', exc_info=True)
        return jsonify([]), 500

@app.route('/thumbnails/<path:filename>')
def serve_thumbnail(filename):
    # Validar el nombre del archivo para prevenir directory traversal
    safe_path = os.path.basename(filename)
    if '..' in safe_path.split(os.path.sep):
        return jsonify({'error': 'Ruta inválida'}), 400

    try:
        # Servir la imagen directamente desde el directorio temp
        file_path = os.path.join(temp_dir, safe_path)
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='image/jpeg')
        else:
            return jsonify({'error': 'Archivo no encontrado'}), 404
    except Exception as e:
        logger.error(f'Error al servir la miniatura {filename}: {str(e)}', exc_info=True)
        return jsonify({'error': 'Error al servir el archivo'}), 500

def _get_sorted_media_entries():
    if not os.path.exists(temp_dir):
        return []

    entries = []
    try:
        entries = [
            entry for entry in os.scandir(temp_dir)
            if entry.is_file() and os.path.splitext(entry.name)[1].lower() in ALLOWED_THUMBNAIL_EXTENSIONS
        ]
        entries.sort(key=lambda e: e.stat().st_mtime, reverse=True)
    except Exception as exc:
        logger.error(f'Error scanning temp_dir for media: {exc}', exc_info=True)
    return entries

@app.route('/api/gallery', methods=['GET'])
def gallery_items():
    try:
        # Obtener la lista de archivos del directorio temp
        files = []
        for filename in os.listdir(temp_dir):
            if any(filename.lower().endswith(ext) for ext in ALLOWED_THUMBNAIL_EXTENSIONS):
                file_path = os.path.join(temp_dir, filename)
                if os.path.isfile(file_path):
                    mtime = os.path.getmtime(file_path)
                    files.append({
                        'filename': filename,
                        'mtime': mtime
                    })
        
        # Ordenar por fecha de modificación (más reciente primero)
        files.sort(key=lambda x: x['mtime'], reverse=True)
        
        host = request.host_url.rstrip('/')
        result = [{
            'id': file_info['filename'],
            'filename': file_info['filename'],
            'url': f"{host}/thumbnails/{file_info['filename']}",
            'timestamp': file_info['mtime']
        } for file_info in files]

        return jsonify(result)
    except Exception as e:
        logger.error(f'Error building gallery response: {str(e)}', exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/extract-text', methods=['POST', 'OPTIONS'])
@cross_origin()
def extract_text():
    if request.method == 'OPTIONS':
        logger.info('[/extract-text] Preflight OPTIONS recibido')
        # Handle preflight request
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response, 200

    try:
        logger.info('[/extract-text] Trigger de OCR recibido desde frontend')
        data = request.get_json()
        if not data or 'image_url' not in data:
            return jsonify({'success': False, 'error': 'No se proporcionó la URL de la imagen'}), 400
        
        image_url = data['image_url']
        logger.info(f'Processing image URL: {image_url}')
        
        # Download the image
        response = requests.get(image_url, stream=True)
        response.raise_for_status()
        
        # Open the image
        img = Image.open(BytesIO(response.content))
        
        # Convert to RGB if needed (required by pytesseract)
        if img.mode != 'RGB':
            img = img.convert('RGB')
            
        # Extract text using pytesseract
        text = pytesseract.image_to_string(img, lang='spa+eng')
        
        # Clean up the extracted text
        text = text.strip()
        
        if not text:
            return jsonify({
                'success': False,
                'error': 'No se pudo extraer texto de la imagen'
            })
            
        logger.info(f'Successfully extracted text: {text[:100]}...')
        
        # Save the extracted text
        save_extracted_text(text)
        
        return jsonify({
            'success': True,
            'text': text
        })
        
    except requests.exceptions.RequestException as e:
        logger.error(f'Error downloading image: {str(e)}')
        return jsonify({
            'success': False,
            'error': f'Error al descargar la imagen: {str(e)}'
        }), 400
    except Exception as e:
        logger.error(f'Error processing image: {str(e)}', exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error al procesar la imagen: {str(e)}'
        }), 500


@app.route('/save-text', methods=['POST', 'OPTIONS'])
@cross_origin()
def save_text_endpoint():
    """Guardar texto recibido desde el frontend en el archivo adecuado."""
    if request.method == 'OPTIONS':
        logger.info('[/save-text] Preflight OPTIONS recibido')
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response, 200

    try:
        logger.info('[/save-text] Trigger de guardado de texto recibido')
        data = request.get_json() or {}
        text = (data.get('text') or '').strip()
        filename = (data.get('filename') or '').strip()

        if not text:
            return jsonify({'success': False, 'error': 'No se proporcionó texto para guardar'}), 400

        if not filename or filename == 'extracted_texts.txt':
            save_extracted_text(text)
            return jsonify({'success': True, 'target': text_file_path})

        safe_filename = filename.replace('\\', '/')
        if '..' in safe_filename:
            return jsonify({'success': False, 'error': 'Nombre de archivo no válido'}), 400

        target_path = os.path.join(base_dir, safe_filename)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        with open(target_path, 'a', encoding='utf-8') as f:
            if os.path.getsize(target_path) > 0:
                f.write('\n')
            f.write(text)

        return jsonify({'success': True, 'target': target_path})

    except Exception as e:
        logger.error(f'Error saving text via /save-text: {str(e)}', exc_info=True)
        return jsonify({'success': False, 'error': f'Error al guardar el texto: {str(e)}'}), 500

def _validate_extracted_texts(min_length: int = 10):
    """Validates that the extracted_texts file exists and has enough content."""
    if not os.path.exists(text_file_path):
        return False, {
            'success': False,
            'error': 'No hay textos para contrastar. Asegúrate de haber guardado textos primero.',
            'metadata': {
                'source_file': text_file_path,
                'length': 0
            }
        }, 400

    with open(text_file_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    if len(content) <= min_length:
        return False, {
            'success': False,
            'error': 'No hay suficiente texto para contrastar',
            'metadata': {
                'source_file': text_file_path,
                'length': len(content)
            }
        }, 400

    return True, {'content': content}, 200


@app.route('/analysis-output', methods=['GET'])
@cross_origin()
def get_analysis_output():
    try:
        if not os.path.exists(analysis_output_path):
            return jsonify({
                'success': False,
                'error': 'output_analisis.txt no existe',
                'source_file': analysis_output_path,
                'length': 0
            }), 404

        with open(analysis_output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return jsonify({
            'success': True,
            'content': content,
            'length': len(content),
            'source_file': analysis_output_path
        })

    except Exception as e:
        logger.error(f'Error al leer output_analisis.txt: {str(e)}', exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error al leer output_analisis.txt: {str(e)}'
        }), 500


@app.route('/contrast-texts', methods=['POST', 'OPTIONS'])
@cross_origin()
def contrast_texts_new():
    """
    Endpoint principal para el botón 'Contrastar' en el frontend.
    Utiliza gemini/inputAnalisistxt.analyze_contrast_texts_from_file.
    """
    if request.method == 'OPTIONS':
        logger.info('[/contrast-texts] Preflight OPTIONS recibido')
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response, 200

    try:
        logger.info('[/contrast-texts] Trigger de contraste recibido desde frontend')
        is_valid, payload, status = _validate_extracted_texts()
        if not is_valid:
            return jsonify(payload), status

        logger.info(f'[/contrast-texts] Ejecutando análisis de contraste. Archivo: {text_file_path}')
        analysis_result = analyze_contrast_texts_from_file(Path(text_file_path))

        if not analysis_result.get('success', False):
            return jsonify({
                'success': False,
                'error': analysis_result.get('error', 'Error desconocido al analizar el texto'),
                'metadata': {
                    'source_file': text_file_path,
                    'length': len(payload.get('content', '')),
                    **analysis_result.get('metadata', {})
                }
            }), 500

        logger.info('[/contrast-texts] Contraste completado correctamente mediante cliente OpenRouter')

        return jsonify({
            'success': True,
            'analysis': analysis_result.get('analysis', '').strip(),
            'metadata': {
                'source_file': text_file_path,
                'length': len(payload.get('content', '')),
                **analysis_result.get('metadata', {})
            }
        })

    except Exception as e:
        logger.error(f'Error en /contrast-texts: {str(e)}', exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error al procesar la solicitud: {str(e)}'
        }), 500


@app.route('/contrast-texts-legacy', methods=['POST', 'OPTIONS'])
@cross_origin()
def contrast_texts_legacy():
    """
    Endpoint legacy: ejecuta gemini/inputTxt.py vía subprocess (flujo anterior).
    """
    if request.method == 'OPTIONS':
        logger.info('[/contrast-texts-legacy] Preflight OPTIONS recibido')
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response, 200

    try:
        logger.info('[/contrast-texts-legacy] Trigger de contraste (legacy) recibido')
        is_valid, payload, status = _validate_extracted_texts()
        if not is_valid:
            return jsonify(payload), status

        gemini_script_path = os.path.join(base_dir, 'gemini', 'inputTxt.py')
        try:
            logger.info(f'[/contrast-texts-legacy] Ejecutando script: {gemini_script_path}')
            result = subprocess.run(
                [sys.executable, gemini_script_path],
                capture_output=True,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            logger.error(f'Error al ejecutar inputTxt.py: {str(e)}')
            logger.error(f'Script stderr: {e.stderr}')
            return jsonify({
                'success': False,
                'error': f'Error al ejecutar el análisis: {e.stderr}',
                'metadata': {
                    'source_file': text_file_path,
                    'length': len(payload.get('content', ''))
                }
            }), 500

        output = result.stdout or ''
        marker = "Respuesta del modelo:"
        idx = output.find(marker)
        analysis_text = output[idx:].strip() if idx != -1 else output.strip()

        return jsonify({
            'success': True,
            'analysis': analysis_text,
            'metadata': {
                'source_file': text_file_path,
                'length': len(payload.get('content', ''))
            }
        })

    except Exception as e:
        logger.error(f'Error en /contrast-texts-legacy: {str(e)}', exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error al contrastar los textos: {str(e)}'
        }), 500


# Endpoint legacy original conservado
@app.route('/analyze-texts', methods=['POST'])
def analyze_texts():
    try:
        is_valid, payload, status = _validate_extracted_texts()
        if not is_valid:
            return jsonify(payload), status

        gemini_script_path = os.path.join(base_dir, 'gemini', 'inputTxt.py')
        try:
            result = subprocess.run(
                [sys.executable, gemini_script_path],
                capture_output=True,
                text=True,
                check=True
            )

            output = result.stdout
            analysis_start = output.find("Respuesta del modelo:")
            analysis_text = output[analysis_start:] if analysis_start != -1 else output

            return jsonify({
                'success': True,
                'analysis': analysis_text,
                'metadata': {
                    'source_file': text_file_path,
                    'length': len(payload.get('content', ''))
                }
            })

        except subprocess.CalledProcessError as e:
            logger.error(f'Error running Gemini script: {str(e)}')
            logger.error(f'Script stderr: {e.stderr}')
            return jsonify({
                'success': False,
                'error': f'Error al ejecutar el análisis: {e.stderr}'
            }), 500

    except Exception as e:
        logger.error(f'Error analyzing texts: {str(e)}', exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error al analizar los textos: {str(e)}'
        }), 500

@app.route('/download-texts')
def download_texts():
    try:
        # Ensure the file exists (create empty if it doesn't)
        if not os.path.exists(text_file_path):
            with open(text_file_path, 'w', encoding='utf-8') as f:
                f.write('Archivo de textos extraídos\n' + '=' * 30 + '\n\n')
            
        # Check if file has content (more than just the header)
        with open(text_file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            
        if len(content) <= 50:  # Just the header or empty
            return jsonify({'error': 'No se han extraído textos aún'}), 404
            
        return send_file(
            text_file_path,
            mimetype='text/plain; charset=utf-8',
            as_attachment=True,
            download_name='textos_extraidos.txt'
        )
    except Exception as e:
        logger.error(f'Error serving text file: {str(e)}', exc_info=True)
        return jsonify({'error': f'Error al descargar los textos: {str(e)}'}), 500


@app.route('/analysis-output', methods=['GET'])
@cross_origin()
def analysis_output():
    """Devuelve el contenido de output_analisis.txt para mostrarlo en el frontend."""
    try:
        if not os.path.exists(analysis_output_path):
            return jsonify({
                'success': False,
                'error': 'output_analisis.txt no existe. Ejecuta un contraste primero.'
            }), 404

        with open(analysis_output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        metadata = {
            'source_file': analysis_output_path,
            'length': len(content),
            'modified': os.path.getmtime(analysis_output_path),
        }

        # Use "text" (and keep "content" for backward compatibility)
        stripped = content.strip()
        return jsonify({
            'success': True,
            'text': stripped,
            'content': stripped,
            'metadata': metadata
        })
    except Exception as e:
        logger.error(f'Error al leer output_analisis.txt: {str(e)}', exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error al leer el archivo: {str(e)}'
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get('MAIN_APP_PORT', '5000'))
    app.run(debug=True, host='0.0.0.0', port=port)
