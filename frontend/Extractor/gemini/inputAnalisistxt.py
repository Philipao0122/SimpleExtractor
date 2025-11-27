import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime


def main():
    result = analyze_contrast_texts_from_file()
    if result["success"]:
        print("\nAnálisis completado:")
        print("-" * 80)
        print(result["analysis"])
        print("-" * 80)
        
        # Guardar en archivo
        try:
            from datetime import datetime
            import os
            
            # Crear directorio de salida si no existe
            output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analisis")
            os.makedirs(output_dir, exist_ok=True)
            
            # Crear nombre de archivo con timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(output_dir, f"analisis_{timestamp}.txt")
            
            # Escribir el análisis en el archivo
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("=== ANÁLISIS POLÍTICO ===\n\n")
                f.write(f"Fecha del análisis: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Archivo analizado: {result.get('metadata', {}).get('source_file', 'N/A')}\n")
                f.write("-" * 80 + "\n\n")
                f.write(result["analysis"])
                f.write("\n\n" + "=" * 80 + "\n")
                f.write("Fin del análisis")
            
            print(f"\n✅ Análisis guardado en: {os.path.abspath(output_file)}")
            
        except Exception as e:
            print(f"\n❌ Error al guardar el archivo: {str(e)}")
    else:
        print(f"\n❌ Error: {result.get('error', 'Error desconocido')}")
def _safe_source_path(file_path):
    """
    Devuelve una representación de ruta segura para JSON (string o None).
    """
    if file_path is None:
        return None
    return str(file_path)


def analyze_contrast_texts_from_file(file_path=None):
    """
    Analiza el contenido de un archivo de texto usando el modelo de OpenAI.
    Si no se proporciona una ruta, usa 'extracted_texts.txt' en el mismo directorio.

    Args:
        file_path (str | Path | None): Ruta al archivo de texto a analizar.

    Returns:
        dict: Un diccionario con los campos:
            - success (bool): Indica si el análisis fue exitoso
            - analysis (str): El resultado del análisis
            - metadata (dict): Metadatos sobre el análisis
            - error (str, opcional): Mensaje de error si algo falla
    """
    try:
        print("Iniciando análisis de contraste...")

        # Cargar variables de entorno (intenta varias ubicaciones)
        env_candidates = [
            Path(__file__).resolve().parent.parent / ".env",   # frontend/Extractor/.env
            Path(__file__).resolve().parents[2] / ".env",      # frontend/.env
            Path(__file__).resolve().parents[3] / ".env",      # raíz del proyecto
        ]
        loaded_env = False
        for env_path in env_candidates:
            if env_path.exists():
                load_dotenv(env_path, override=False)
                loaded_env = True
                break
        if not loaded_env:
            print("Aviso: no se encontró .env en rutas conocidas; se intentará usar las variables de entorno existentes.")

        # Verificar API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            error_msg = "Error: OPENAI_API_KEY no está configurada en el entorno"
            print(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "metadata": {"source_file": _safe_source_path(file_path)},
            }

        # Establecer la ruta por defecto si no se proporciona
        if file_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(script_dir, "extracted_texts.txt")

        print(f"Leyendo archivo: {file_path}")

        # Leer el archivo
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                texto = f.read().strip()

            if not texto:
                error_msg = (
                    "El archivo está vacío. No hay texto para analizar."
                )
                print(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "metadata": {
                        "source_file": _safe_source_path(file_path),
                        "length": 0,
                    },
                }

            print(
                f"Texto leído correctamente. Tamaño: {len(texto)} caracteres"
            )

            # Configurar el cliente de OpenAI
            client = OpenAI(api_key=api_key)

            # Crear el prompt para análisis político
            prompt = f"""
            # 📰 Rol Ligero de Analista Comparativo de Noticias

## 🎯 Rol
Eres un **analista comparativo de noticias**. Tu trabajo es **contrastar de manera clara, breve y profesional** entre 2 y 4 fuentes informativas sobre un mismo tema.  
No realizas análisis geopolíticos complejos.  
Tu enfoque está en **cómo los medios construyen el mensaje**.

---

## 🧩 Objetivo
Detectar:
- Sesgos
- Tono y lenguaje
- Enfoque narrativo
- Actores responsabilizados o favorecidos
- Omisiones relevantes
- Posible impacto en la percepción del lector

---

## 📘 Instrucciones para el análisis

### **1. Foco principal de cada noticia**  
Resume en 2–3 líneas qué destaca cada fuente, qué prioriza y qué deja fuera.

---

### **2. Tono y lenguaje**
Indica si el lenguaje es:
- Neutral  
- Crítico  
- Alarmista  
- Técnico  
- Institucional  
- Político (pro/oposición, pro/gobierno)  
- Emocional o cargado  

---

### **3. Sesgo o encuadre narrativo**  
Identifica los posibles sesgos:
- Político  
- Emocional  
- Institucional  
- Pro-gobierno / anti-gobierno  
- Pro-oposición / anti-oposición  
- Enfoque en culpabilidad vs. enfoque explicativo  

---

### **4. Actor responsabilizado o favorecido**  
Indica:
- ¿A quién señala cada medio como responsable?  
- ¿A quién protege, suaviza o exculpa?  
- ¿Quién queda reforzado en el relato?

---

### **5. Comparación breve (tabla)**

| Aspecto | Fuente A | Fuente B | Fuente C (opcional) | Fuente D (opcional) |
|---------|----------|----------|----------------------|----------------------|
| **Enfoque** | | | | |
| **Tono** | | | | |
| **Sesgo** | | | | |
| **Responsable señalado** | | | | |
| **Mensaje implícito** | | | | |

---

### **6. Conclusión ligera (5–7 líneas)**  
Un párrafo final donde sintetices:
- Qué fuentes son más críticas o más técnicas  
- Quién construye un relato más político o más institucional  
- Cómo cambian los énfasis entre fuentes  
- Qué efectos podría tener en la opinión pública  

---

## 📌 Ejemplo de Formato de Salida


            Texto a analizar:
            {texto}

            Por favor, organiza la respuesta de manera clara y estructurada, utilizando encabezados y viñetas para facilitar la lectura. Mantén un tono profesional y objetivo en todo momento, respaldando tus observaciones con ejemplos concretos del texto cuando sea posible.
            """

            print("\nEnviando solicitud al modelo...")

            # Llamar al modelo
            completion = client.chat.completions.create(
                model="gpt-5",
                messages=[{"role": "user", "content": prompt}],
            )

            # Obtener la respuesta
            analysis_result = completion.choices[0].message.content

            # Guardar el análisis en output_analisis.txt
            output_path = Path(__file__).parent / "output_analisis.txt"
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write("=== ANÁLISIS COMPARATIVO ===\n\n")
                    f.write(analysis_result)
                print(f"\n✅ Análisis guardado en: {output_path}")
            except Exception as e:
                print(f"\n⚠️ No se pudo guardar el análisis en {output_path}: {str(e)}")

            print("\nAnálisis completado exitosamente")

            return {
                "success": True,
                "analysis": analysis_result,
                "metadata": {
                    "source_file": _safe_source_path(file_path),
                    "output_file": str(output_path),
                    "length": len(texto),
                },
            }

        except FileNotFoundError:
            error_msg = f"Error: No se encontró el archivo en {file_path}"
            print(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "metadata": {"source_file": _safe_source_path(file_path)},
            }

    except Exception as e:
        error_msg = f"Error inesperado: {str(e)}"
        print(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "metadata": {
                "source_file": _safe_source_path(
                    file_path if "file_path" in locals() else None
                )
            },
        }


# Mantener la función main para compatibilidad
def main():
    result = analyze_contrast_texts_from_file()
    if result["success"]:
        print("\nAnálisis completado:")
        print("-" * 50)
        print(result["analysis"])
        print("-" * 50)
    else:
        print(f"\nError: {result.get('error', 'Error desconocido')}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAnálisis cancelado por el usuario.")
        sys.exit(0)
    except Exception as e:
        print(f"\nError inesperado: {e}")
        sys.exit(1)
