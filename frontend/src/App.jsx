import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import DeckForm from './components/DeckForm';
import GenerationProgress from './components/GenerationProgress';
import SlideGallery from './components/SlideGallery';
import NonCodingErrorModal from './components/NonCodingErrorModal';

export default function App() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('studio_theme') || 'dark';
  });
  const [colleges, setColleges] = useState([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [currentDeckId, setCurrentDeckId] = useState(null);
  const [deckData, setDeckData] = useState(null);
  const [nonCodingError, setNonCodingError] = useState(null);
  const [suggestedTopic, setSuggestedTopic] = useState(null);

  const isDark = theme === 'dark';

  useEffect(() => {
    localStorage.setItem('studio_theme', theme);
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [theme]);

  useEffect(() => {
    fetchInitialData();
  }, []);

  const fetchInitialData = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/templates');
      if (res.ok) {
        const data = await res.json();
        setColleges(data.colleges || []);
      }
    } catch (err) {
      console.error('Error loading templates:', err);
    }
  };

  const handleToggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  const handleGenerate = async (formData) => {
    setNonCodingError(null);
    setIsGenerating(true);
    setStatusMessage('Initiating topic validation and curriculum planning...');
    setDeckData(null);

    try {
      const res = await fetch('http://localhost:8000/api/decks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });

      if (!res.ok) {
        const err = await res.json();
        setIsGenerating(false);
        if (err.detail && err.detail.error === 'NON_CODING_TOPIC') {
          setNonCodingError(err.detail);
        } else {
          alert(err.detail ? (err.detail.message || JSON.stringify(err.detail)) : 'Generation failed');
        }
        return;
      }

      const data = await res.json();
      const deckId = data.deck_id;
      setCurrentDeckId(deckId);

      // Start polling status
      pollDeckStatus(deckId);
    } catch (err) {
      console.error('Error submitting deck form:', err);
      setIsGenerating(false);
      alert('Network or server error while connecting to backend.');
    }
  };

  const pollDeckStatus = (deckId) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/decks/${deckId}`);
        if (res.ok) {
          const data = await res.json();
          setStatusMessage(data.status_message || 'Processing...');

          if (data.status === 'completed') {
            clearInterval(interval);
            setIsGenerating(false);
            setDeckData(data);
          } else if (data.status === 'failed') {
            clearInterval(interval);
            setIsGenerating(false);
            alert(`Generation failed: ${data.status_message}`);
          }
        }
      } catch (e) {
        console.error('Polling error:', e);
      }
    }, 1500);
  };

  const handleDownload = () => {
    if (!currentDeckId) return;
    window.open(`http://localhost:8000/api/decks/${currentDeckId}/download`, '_blank');
  };

  return (
    <div className={`min-h-screen flex flex-col transition-colors duration-200 ${
      isDark ? 'bg-[#080C14] text-gray-100' : 'bg-[#F8FAFC] text-gray-900'
    }`}>
      <Navbar theme={theme} onToggleTheme={handleToggleTheme} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Main User Input Form */}
        <DeckForm
          colleges={colleges}
          onGenerate={handleGenerate}
          isGenerating={isGenerating}
          initialData={suggestedTopic}
          theme={theme}
        />

        {/* Realtime Generation Progress */}
        {isGenerating && (
          <GenerationProgress statusMessage={statusMessage} theme={theme} />
        )}

        {/* Verified Slide Deck Gallery */}
        {deckData && (
          <SlideGallery deck={deckData} onDownload={handleDownload} theme={theme} />
        )}
      </main>

      {/* Non-Coding Topic Friendly Rejection Modal */}
      {nonCodingError && (
        <NonCodingErrorModal
          error={nonCodingError}
          onClose={() => setNonCodingError(null)}
          onSelectSuggestedTopic={(topic) => setSuggestedTopic(topic)}
          theme={theme}
        />
      )}
    </div>
  );
}
