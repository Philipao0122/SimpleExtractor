import { useState, useEffect } from 'react';
import axios from 'axios';
import { InfiniteCarousel } from './components/InfiniteCarousel';

// Configure axios to include credentials if needed
axios.defaults.withCredentials = false; // Set to true if your backend requires credentials

interface ImageItem {
  id: string;
  url: string;
  timestamp: number;
  extractedText?: string;
  processing?: boolean;
  error?: string;
  analysis?: string;
}

interface ApiResponse {
  success: boolean;
  image_url?: string;
  error?: string;
  text?: string;
}

interface ExtractTextResponse {
  success: boolean;
  text?: string;
  error?: string;
}

interface ExtractImageResponse {
  success: boolean;
  image_url?: string;
  error?: string;
}

interface AnalyzeTextsResponse {
  success: boolean;
  analysis?: string;
  error?: string;
  metadata?: {
    source_file?: string;
    length?: number;
  };
}

interface ThumbnailItem {
  url: string;
  id: string;
  timestamp: string;
  filename: string; // Add this line

}
// Add this with your other interfaces (around line 20-40)
interface InfiniteCarouselProps {
  images: Array<{ src: string; alt: string; id: string }>;
  height: number;
  gap: number;
  speed: number;
  direction: 'left' | 'right';
  pauseOnHover: boolean;
  rounded: boolean;
  onImageClick?: (image: { src: string; alt: string; id: string }) => void;
  selectedImageId?: string | null;
}

const ThumbnailCarousel: React.FC<{
  thumbnails: ThumbnailItem[];
  onThumbnailClick: (thumbnail: ThumbnailItem) => void;
  selectedThumbnailId: string | null;
}> = ({ thumbnails, onThumbnailClick, selectedThumbnailId }) => {
  if (thumbnails.length === 0) return null;

  const carouselImages = thumbnails.map(thumb => ({
    src: thumb.url,
    alt: `Thumbnail ${thumb.filename}`,
    id: thumb.id
  }));

  return (
    <div className="w-full max-w-6xl mx-auto mt-8">
      <InfiniteCarousel 
        images={carouselImages}
        height={210}
        gap={12}
        speed={20}
        direction="left"
        pauseOnHover={true}
        rounded={true}
        onImageClick={(image) => {
          const selected = thumbnails.find(t => t.id === image.id);
          if (selected) {
            onThumbnailClick(selected);
          }
        }}
        selectedImageId={selectedThumbnailId}
      />
    </div>
  );
};

export default function ImageExtractor() {
  const [url, setUrl] = useState('');
  const [images, setImages] = useState<ImageItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState('');
  const [analysisMetadata, setAnalysisMetadata] = useState<{ source_file?: string; length?: number } | null>(null);
  const [thumbnails, setThumbnails] = useState<ThumbnailItem[]>([]);
  const [isLoadingThumbnails, setIsLoadingThumbnails] = useState(false);
  const [selectedThumbnail, setSelectedThumbnail] = useState<ThumbnailItem | null>(null); // Add this line
// Función auxiliar para procesar y guardar textos
const processAndSaveTexts = async (texts: string[]): Promise<boolean> => {
  if (!texts.length) {
    console.log('No hay textos para procesar');
    return false;
  }

  try {
    const timestamp = new Date().toISOString();
    const formattedTexts = texts
      .filter(text => text && text.trim().length > 0)
      .map((text, index) => `--- Texto ${index + 1} (${timestamp}) ---\n${text.trim()}\n`)
      .join('\n\n');

    if (!formattedTexts) {
      console.log('No hay textos válidos para guardar');
      return false;
    }

    const response = await axios.post('http://localhost:5000/save-text', {
      text: formattedTexts,
      filename: 'gemini/extracted_texts.txt'
    });
   return (response.data as any).success;

  } catch (error) {
    console.error('Error al guardar los textos:', error);
    return false;
  }
};
  // Load thumbnails from the server
  const fetchThumbnails = async () => {
    try {
      setIsLoadingThumbnails(true);
      const response = await axios.get<string[]>('http://localhost:5001/api/thumbnails');
      // The API returns a direct array of filenames
      if (Array.isArray(response.data)) {
        const now = Date.now();
        const newThumbnails: ThumbnailItem[] = response.data
          .filter((filename: string) => filename && typeof filename === 'string')
          .map((filename: string, index: number) => ({
            id: `thumb-${now}-${index}`,
            url: `http://localhost:5001/thumbnails/${filename}`,
            timestamp: now.toString(),
            filename:  filename
          }));
        
        console.log('Fetched thumbnails:', newThumbnails); // Debug log
        setThumbnails(newThumbnails);
      } else {
        console.error('Unexpected response format:', response.data);
        setThumbnails([]);
      }
    } catch (error) {
      console.error('Error fetching thumbnails:', error);
      setThumbnails([]);
    } finally {
      setIsLoadingThumbnails(false);
    }
  };


  // Add this function to handle OCR extraction
const extractTextFromImage = async (imageUrl: string): Promise<string> => {
  try {
    const response = await axios.post<{ text: string }>('http://localhost:5000/extract-text', {
      image_url: imageUrl
    });
    return response.data.text || '';
  } catch (error) {
    console.error('Error extracting text:', error);
    return '';
  }
};

// Update the handleThumbnailClick function
const handleThumbnailClick = async (thumbnail: ThumbnailItem) => {
  console.log('--- THUMBNAIL CLICKED ---');
  console.log('Thumbnail ID:', thumbnail.id);
  console.log('Filename:', thumbnail.filename);
  
  // Toggle selection
  if (selectedThumbnail?.id === thumbnail.id) {
    console.log('Deselecting thumbnail:', thumbnail.id);
    setSelectedThumbnail(null);
    return;
  }

  console.log('Selecting thumbnail:', thumbnail.id);
  setSelectedThumbnail(thumbnail);
  
  // Add to main view if not already there
  const isAlreadyAdded = images.some(img => img.id === thumbnail.id);
  if (!isAlreadyAdded && images.length < 4) {
    console.log('Adding to main view:', thumbnail.filename);
    const newImage: ImageItem = {
      id: thumbnail.id,
      url: thumbnail.url,
      timestamp: Date.now()
    };
    
    // Extract text from the image
    try {
      const extractedText = await extractTextFromImage(thumbnail.url);
      if (extractedText) {
        console.log('Text extracted successfully');
        // Save to extracted_texts.txt via the backend
        await axios.post('http://localhost:5000/save-text', {
          text: extractedText,
          filename: 'extracted_texts.txt'
        });
      }
    } catch (error) {
      console.error('Error processing image text:', error);
    }
    
    // Update the UI
    setImages(prev => [...prev, newImage]);
    localStorage.setItem('savedInstagramImages', JSON.stringify([...images, newImage]));
  } else if (isAlreadyAdded) {
    console.log('Image already in main view:', thumbnail.filename);
  } else {
    console.log('Maximum number of images (4) reached');
    setError('Has alcanzado el límite de 4 imágenes');
    setTimeout(() => setError(''), 3000);
  }
};


  // Load saved images from localStorage on component mount
  useEffect(() => {
    fetchThumbnails();
    const savedImages = localStorage.getItem('savedInstagramImages');
    if (savedImages) {
      try {
        const parsed = JSON.parse(savedImages);
        const cleanedImages = parsed.map((img: any) => ({
          id: img.id || Date.now().toString(),
          url: img.url,
          timestamp: img.timestamp || Date.now()
        }));
        setImages(cleanedImages);
      } catch (e) {
        console.error('Error parsing saved images:', e);
      }
    }
  }, []);

  // Add this near your other useEffect hooks
useEffect(() => {
  console.log('--- DEBUG ---');
  console.log('Selected Thumbnail:', selectedThumbnail);
  console.log('Current Images:', images);
  console.log('All Thumbnails:', thumbnails);
  console.log('--- END DEBUG ---');
}, [selectedThumbnail, images, thumbnails]);

  // Unified function to extract text and analyze with Gemini
  // Unified function to extract text and analyze with Gemini
const contrastImages = async () => {
  if (isAnalyzing) {
    console.log('Contraste detectado: ya hay una ejecución en curso, se ignora la nueva petición.');
    return;
  }

  console.log('Contraste: iniciando flujo con gemini/extracted_texts.txt como fuente.');
  setIsAnalyzing(true);
  setError('');
  setAnalysisResult('');
  setAnalysisMetadata(null);
  // Add this helper function inside your ImageExtractor component
const joinUrl = (base: string, path: string): string => {
  return `${base.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`;
};

// Add this constant with your other constants
const API_BASE = 'http://localhost:5000'; // Make sure this matches your backend URL

  try {
    const response = await axios.post<AnalyzeTextsResponse>(
  joinUrl(API_BASE, '/contrast-texts'),
  {}, // Empty request body
  {
    headers: {
      'Content-Type': 'application/json',
    },
  }
);
    console.log('Contraste: respuesta recibida', response.data);

    if (response.data.success) {
      const payload = (response.data.analysis || '').trim();
      setAnalysisResult(payload);
      setAnalysisMetadata(response.data.metadata || null);

      if (!payload) {
        const warning = 'El archivo extracted_texts.txt existe pero no contiene datos';
        console.warn('Contraste: ', warning);
        setError(warning);
      }
    } else {
      const errMsg = response.data.error || 'El servicio de contraste regresó sin éxito';
      console.warn('Contraste: respuesta con error', response.data);
      setAnalysisMetadata(response.data.metadata || null);
      setAnalysisResult(response.data.analysis || '');
      setError(errMsg);
    }
  } catch (err) {
    console.error('Contraste: no se pudo contactar con el servicio de backend', err);
    setError('No se pudo completar el contraste. Revisa la terminal para más detalle.');
  } finally {
    setIsAnalyzing(false);
  }
};

const handleExtract = async () => {
    if (!url.trim()) {
      setError('Por favor ingresa una URL de Instagram');
      return;
    }
    if (images.length >= 4) {
      setError('Has alcanzado el límite de 4 imágenes');
      return;
    }
    setIsLoading(true);
    setError('');
    try {
      const response = await axios.post<ExtractImageResponse>('http://localhost:5000/extract-image', { url: url.trim() });
      const responseData = response.data;
      
      if (responseData.success && responseData.image_url) {
        const newImage = {
          id: Date.now().toString(),
          url: responseData.image_url,
          timestamp: Date.now()
        };
        const updatedImages = [...images, newImage];
        setImages(updatedImages);
        localStorage.setItem('savedInstagramImages', JSON.stringify(updatedImages));
        setUrl(''); // Clear the input after successful extraction
      } else {
        throw new Error(responseData.error || 'No se pudo obtener la imagen');
      }
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Error desconocido al extraer la imagen';
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="p-4">
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-4">Extractor de Imágenes de Instagram</h1>
        <div className="flex flex-col gap-4">
          <div className="flex gap-2">
            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="Pega la URL de Instagram"
              className="flex-1 p-2 border rounded"
            />
            <button
              onClick={handleExtract}
              disabled={isLoading}
              className="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600 disabled:bg-blue-300 whitespace-nowrap"
            >
              {isLoading ? 'Extrayendo...' : 'Extraer Imagen'}
            </button>
          </div>
          <div>
            <button
              onClick={contrastImages}
              disabled={isAnalyzing}
              className={`bg-purple-600 text-white px-4 py-2 rounded hover:bg-purple-700 ${
                isAnalyzing ? 'opacity-50 cursor-not-allowed' : ''
              }`}
            >
              {isAnalyzing ? 'Analizando...' : 'Contrastar'}
            </button>

            {analysisResult ? (
              <div className="mt-3 rounded-lg border border-purple-200 bg-white p-3 text-sm text-gray-700 shadow-sm max-h-64 overflow-y-auto whitespace-pre-wrap">
                <p className="mb-1 text-xs text-gray-500">
                  Fuente: {analysisMetadata?.source_file?.split('/')?.pop() || 'extracted_texts.txt'} ·{' '}
                  {analysisMetadata?.length ?? analysisResult.length} caracteres
                </p>
                <div>{analysisResult}</div>
              </div>
            ) : null}
          </div>
        </div>
        {error && <p className="text-red-500 mt-2">{error}</p>}
      </div>
      <div className="mt-6">
        {images.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
            {images.map((img) => (
              <div key={img.id} className="relative group">
                <img 
                  src={img.url} 
                  alt={`Instagram ${img.id}`} 
                  className="w-full max-h-[80vh] object-contain rounded-lg bg-gray-100"
                  style={{ maxWidth: '100%', height: '40vh' }}
                />
                <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-50 transition-all duration-300 rounded-lg flex items-center justify-center opacity-0 group-hover:opacity-100">
                  <button
                    onClick={() => {
                      const newImages = images.filter(i => i.id !== img.id);
                      setImages(newImages);
                      localStorage.setItem('savedInstagramImages', JSON.stringify(newImages));
                    }}
                    className="bg-red-500 text-white p-2 rounded-full hover:bg-red-600 transition-colors"
                    title="Eliminar imagen"
                  >
                    🗑️
                  </button>
                </div>
                
                {/* Image Info Overlay */}
                <div className="absolute bottom-0 left-0 right-0 p-2 space-y-1">
                  {/* Timestamp */}
                  <div className="bg-black bg-opacity-50 text-white text-xs px-2 py-1 rounded inline-block">
                    {new Date(img.timestamp).toLocaleTimeString()}
                  </div>
                  
                  {/* Extracted Text Preview */}
                  {img.extractedText && (
                    <div className="bg-black bg-opacity-70 text-white text-xs p-2 rounded max-h-20 overflow-y-auto">
                      <p className="break-words">
                        {img.extractedText.length > 100 
                          ? `${img.extractedText.substring(0, 100)}...` 
                          : img.extractedText}
                      </p>
                    </div>
                  )}
                  
                  {/* Analysis Preview */}
                  {img.analysis && (
                    <div className="bg-purple-800 bg-opacity-80 text-white text-xs p-2 rounded max-h-20 overflow-y-auto mt-1">
                      <p className="break-words">
                        {img.analysis.length > 100 
                          ? `${img.analysis.substring(0, 100)}...` 
                          : img.analysis}
                      </p>
                    </div>
                  )}
                  
                  {/* Error Message */}
                  {img.error && (
                    <div className="bg-red-600 bg-opacity-80 text-white text-xs p-2 rounded">
                      Error: {img.error}
                    </div>
                  )}
                  
                  {/* Processing Indicator */}
                  {img.processing && (
                    <div className="bg-blue-600 bg-opacity-80 text-white text-xs p-2 rounded flex items-center">
                      <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-white mr-2"></div>
                      Procesando...
                    </div>
                  )}
                  
                  {/* Analyzing Indicator */}
                  {isAnalyzing && (
                    <div className="bg-purple-600 bg-opacity-80 text-white text-xs p-2 rounded flex items-center mt-1">
                      <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-white mr-2"></div>
                      Analizando con Gemini...
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
        
      </div>

     {isLoadingThumbnails ? (
  <div className="flex justify-center items-center h-64">
    <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
  </div>
) : thumbnails.length > 0 ? (
  <ThumbnailCarousel 
    thumbnails={thumbnails} 
    onThumbnailClick={handleThumbnailClick}
    selectedThumbnailId={selectedThumbnail?.id || null}
  />
) : (
  <div className="text-center text-gray-500 py-8 border-2 border-dashed rounded-lg">
    No hay miniaturas disponibles. El servidor de miniaturas puede estar inactivo.
  </div>
)}
      {error && (
        <p className="text-red-500 mt-2 p-2 bg-red-50 rounded">
          {error}
        </p>
      )}
    </div>
  );


  // Add this component at the bottom of your file, before the last closing tag
const InfiniteCarousel: React.FC<InfiniteCarouselProps> = ({ 
  images, 
  height, 
  gap, 
  speed, 
  direction, 
  pauseOnHover, 
  rounded,
  onImageClick,
  selectedImageId
}) => {
  // You can add carousel animation logic here if needed
  // For now, we'll just render the images in a row

  return (
    <div className="overflow-hidden">
      <div 
        className="flex" 
        style={{ 
          gap: `${gap}px`,
          animation: `${
            direction === 'left' ? 'slideLeft' : 'slideRight'
          } ${speed}s linear infinite`
        }}
      >
        {images.map((image) => (
          <div 
            key={image.id}
            className={`
              relative
              ${rounded ? 'rounded-lg overflow-hidden' : ''}
              transition-all duration-300
              ${selectedImageId === image.id ? 'ring-4 ring-blue-500' : ''}
              ${pauseOnHover ? 'hover:animation-pause' : ''}
            `}
            style={{ 
              height: `${height}px`,
              minWidth: `${height * 1.5}px`
            }}
          >
            <img
              src={image.src}
              alt={image.alt}
              onClick={() => onImageClick?.(image)}
              className={`
                h-full w-full object-cover
                ${rounded ? 'rounded-lg' : ''}
                transition-transform duration-300
                hover:scale-105
                cursor-pointer
              `}
            />
          </div>
        ))}
      </div>
    </div>
  );
};
}
