import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import Stepper from './components/Stepper';
import DeckForm from './components/DeckForm';
import GenerationProgress from './components/GenerationProgress';
import SlideGallery from './components/SlideGallery';
import NonCodingErrorModal from './components/NonCodingErrorModal';
import ExportCenterModal from './components/ExportCenterModal';
import SingleSlideRegenModal from './components/SingleSlideRegenModal';
import VersionMigrationModal from './components/VersionMigrationModal';
import LiveClassModeModal from './components/LiveClassModeModal';
import HistoryModal from './components/HistoryModal';

export default function App() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('studio_theme') || 'dark';
  });
  const [colleges, setColleges] = useState([]);
  const [runtimes, setRuntimes] = useState([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [currentDeckId, setCurrentDeckId] = useState(null);
  const [deckData, setDeckData] = useState(null);
  const [materialsData, setMaterialsData] = useState(null);
  const [nonCodingError, setNonCodingError] = useState(null);
  const [suggestedTopic, setSuggestedTopic] = useState(null);
  const [generationProgress, setGenerationProgress] = useState(null);
  const [activeStep, setActiveStep] = useState(1);

  // Modals
  const [showExportModal, setShowExportModal] = useState(false);
  const [showRegenModal, setShowRegenModal] = useState(false);
  const [regenSlideIndex, setRegenSlideIndex] = useState(0);
  const [showMigrationModal, setShowMigrationModal] = useState(false);
  const [showLiveModeModal, setShowLiveModeModal] = useState(false);
  const [showHistoryModal, setShowHistoryModal] = useState(false);

  const isDark = theme === 'dark';

  useEffect(() => {
    localStorage.setItem('studio_theme', theme);
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [theme]);

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

    try {
      const runtimesRes = await fetch('http://localhost:8000/api/runtimes');
      if (runtimesRes.ok) {
        const runtimesData = await runtimesRes.json();
        setRuntimes(runtimesData.tracks || []);
      }
    } catch (err) {
      console.error('Error loading runtimes:', err);
    }
  };

  useEffect(() => {
    fetchInitialData();
  }, []);

  const handleToggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  const handleGenerate = async (formData) => {
    setNonCodingError(null);
    setIsGenerating(true);
    setStatusMessage('Initiating topic validation and curriculum planning...');
    setDeckData(null);
    setMaterialsData(null);

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
      setActiveStep(2);

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
          if (data.generation_progress) {
            setGenerationProgress(data.generation_progress);
          }

          if (data.status === 'completed') {
            clearInterval(interval);
            setIsGenerating(false);
            setDeckData(data);
            setActiveStep(3);
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

  const loadDeckById = async (deckId) => {
    try {
      const res = await fetch(`http://localhost:8000/api/decks/${deckId}`);
      if (res.ok) {
        const data = await res.json();
        setDeckData(data);
        setCurrentDeckId(deckId);
        if (data.materials_status === 'ready') {
          setActiveStep(5);
          fetchMaterials(deckId);
        } else if (data.approved) {
          setActiveStep(4);
        } else {
          setActiveStep(3);
        }
      }
    } catch (e) {
      console.error('Failed to load deck:', e);
    }
  };

  const fetchMaterials = async (deckId) => {
    try {
      const res = await fetch(`http://localhost:8000/api/decks/${deckId}/materials`);
      if (res.ok) {
        const data = await res.json();
        setMaterialsData(data);
      }
    } catch (e) {
      console.error('Error fetching materials:', e);
    }
  };

  const handleApproveDeck = async () => {
    if (!currentDeckId) return;
    try {
      const res = await fetch(`http://localhost:8000/api/decks/${currentDeckId}/approve`, {
        method: 'POST',
      });
      if (res.ok) {
        const updated = await res.json();
        setDeckData((prev) => ({
          ...prev,
          approved: true,
          approved_at: updated.approved_at,
        }));
        setActiveStep(5);
      } else {
        const err = await res.json();
        alert(`Approval error: ${err.detail || 'Could not approve deck'}`);
      }
    } catch (e) {
      console.error(e);
      alert('Network error approving deck');
    }
  };

  const handleDownloadDeck = () => {
    if (!currentDeckId) return;
    window.open(`http://localhost:8000/api/decks/${currentDeckId}/download`, '_blank');
  };

  const handleRegeneratedSlide = (result) => {
    if (result && deckData) {
      const updatedSlides = [...(deckData.slides || [])];
      if (result.slide_index < updatedSlides.length) {
        updatedSlides[result.slide_index] = result.new_slide;
      }
      const updatedPreviews = [...(deckData.preview_paths || [])];
      if (result.preview_path && result.slide_index < updatedPreviews.length) {
        updatedPreviews[result.slide_index] = result.preview_path;
      }
      setDeckData({
        ...deckData,
        slides: updatedSlides,
        preview_paths: updatedPreviews,
      });
    }
  };

  const handleMigratedDeck = () => {
    if (currentDeckId) {
      loadDeckById(currentDeckId);
    }
  };

  const deckState = {
    hasDeck: !!deckData,
    verified: !!(deckData?.verified),
    approved: !!(deckData?.approved),
    materialsReady: deckData?.materials_status === 'ready',
  };

  return (
    <div
      className={`min-h-screen flex flex-col transition-colors duration-200 ${
        isDark ? 'bg-[#080C14] text-gray-100' : 'bg-[#F8FAFC] text-gray-900'
      }`}
    >
      <Navbar
        theme={theme}
        onToggleTheme={handleToggleTheme}
        hasDeck={!!deckData}
        onOpenLiveMode={() => setShowLiveModeModal(true)}
        onOpenHistory={() => setShowHistoryModal(true)}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Step-by-Step Studio Stepper */}
        <Stepper
          currentStep={activeStep}
          onSelectStep={(step) => {
            setActiveStep(step);
            if (step === 6) setShowExportModal(true);
          }}
          theme={theme}
          deckState={deckState}
        />

        {/* Form is visible on Step 1 or whenever no deck is active */}
        {(!deckData || activeStep === 1) && (
          <DeckForm
            colleges={colleges}
            runtimes={runtimes}
            onGenerate={handleGenerate}
            isGenerating={isGenerating}
            initialData={suggestedTopic}
            theme={theme}
          />
        )}

        {/* Realtime Generation Progress */}
        {isGenerating && (
          <GenerationProgress
            statusMessage={statusMessage}
            progress={generationProgress}
            theme={theme}
          />
        )}

        {/* Verified Slide Deck Gallery + Supporting Materials */}
        {deckData && !isGenerating && (
          <SlideGallery
            deck={deckData}
            theme={theme}
            isApproved={deckData.approved}
            onApprove={handleApproveDeck}
            onDownload={handleDownloadDeck}
            onOpenExport={() => setShowExportModal(true)}
            onOpenRegenerate={(slideIdx) => {
              setRegenSlideIndex(slideIdx || 0);
              setShowRegenModal(true);
            }}
            onOpenMigration={() => setShowMigrationModal(true)}
            onOpenLiveMode={() => setShowLiveModeModal(true)}
          />
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

      {/* Export Center Modal */}
      {showExportModal && currentDeckId && (
        <ExportCenterModal
          deckId={currentDeckId}
          onClose={() => setShowExportModal(false)}
          theme={theme}
        />
      )}

      {/* Single Slide Regenerator Modal */}
      {showRegenModal && currentDeckId && deckData && (
        <SingleSlideRegenModal
          deckId={currentDeckId}
          slides={deckData.slides || []}
          initialSlideIndex={regenSlideIndex}
          onClose={() => setShowRegenModal(false)}
          onRegenerated={handleRegeneratedSlide}
          theme={theme}
        />
      )}

      {/* Version Migration Modal */}
      {showMigrationModal && currentDeckId && deckData && (
        <VersionMigrationModal
          deckId={currentDeckId}
          currentTech={deckData.tech}
          currentVersion={deckData.tech_version}
          onClose={() => setShowMigrationModal(false)}
          onMigrated={handleMigratedDeck}
          theme={theme}
        />
      )}

      {/* Fullscreen Live Class Trainer Mode Modal */}
      {showLiveModeModal && deckData && (
        <LiveClassModeModal
          deck={deckData}
          materials={materialsData}
          onClose={() => setShowLiveModeModal(false)}
          theme={theme}
        />
      )}

      {/* Studio History Modal */}
      {showHistoryModal && (
        <HistoryModal
          onSelectDeck={loadDeckById}
          onClose={() => setShowHistoryModal(false)}
          theme={theme}
        />
      )}
    </div>
  );
}
