import { useState, useEffect, useRef } from 'react';

/**
 * Compact working directory input component.
 *
 * Shows current cwd inline and allows editing before first query.
 * For existing sessions, displays read-only cwd.
 * Designed to fit in a status bar alongside other elements.
 *
 * @param {boolean} isEditable - Whether the cwd can be edited (new session)
 * @param {Object} cwdInfo - Current cwd info for new sessions { cwd, shortened }
 * @param {Function} onCwdChange - Callback when cwd changes, receives { cwd, shortened }
 * @param {string} currentCwd - Current cwd for existing sessions (from tab.current_cwd)
 */
export function CwdInput({ isEditable, cwdInfo, onCwdChange, currentCwd }) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const [validationState, setValidationState] = useState(null); // null | 'validating' | 'valid' | 'will_create' | 'error'
  const [errorMessage, setErrorMessage] = useState('');
  const inputRef = useRef(null);
  const containerRef = useRef(null);

  // Focus input when entering edit mode
  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  // Exit editing mode when isEditable becomes false (e.g., after sending query)
  useEffect(() => {
    if (!isEditable && isEditing) {
      setIsEditing(false);
      setValidationState(null);
      setErrorMessage('');
    }
  }, [isEditable, isEditing]);

  const handleStartEdit = () => {
    if (!isEditable) return;
    setIsEditing(true);
    setEditValue(cwdInfo?.cwd || '');
    setValidationState(null);
    setErrorMessage('');
  };

  const handleValidate = async (value) => {
    const trimmed = value.trim();
    if (!trimmed) {
      setValidationState('error');
      setErrorMessage('Path cannot be empty');
      return false;
    }

    setValidationState('validating');

    try {
      const res = await fetch('/api/validate-cwd', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: trimmed })
      });
      const data = await res.json();

      if (data.valid) {
        setValidationState(data.will_create ? 'will_create' : 'valid');
        setErrorMessage('');
        onCwdChange?.({ cwd: data.resolved_path, shortened: data.shortened });
        return true;
      } else {
        setValidationState('error');
        setErrorMessage(data.error || 'Invalid path');
        return false;
      }
    } catch (err) {
      setValidationState('error');
      setErrorMessage('Failed to validate path');
      return false;
    }
  };

  const handleConfirm = async () => {
    const isValid = await handleValidate(editValue);
    if (isValid) {
      setIsEditing(false);
    }
  };

  const handleCancel = () => {
    setIsEditing(false);
    setEditValue(cwdInfo?.cwd || '');
    setValidationState(null);
    setErrorMessage('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleConfirm();
    } else if (e.key === 'Escape') {
      handleCancel();
    }
  };

  // Handle clicks outside to cancel (but not if there's an error)
  useEffect(() => {
    if (!isEditing) return;

    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        if (validationState === 'error') return;
        handleCancel();
      }
    };

    const timeoutId = setTimeout(() => {
      document.addEventListener('mousedown', handleClickOutside);
    }, 100);

    return () => {
      clearTimeout(timeoutId);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isEditing, validationState]);

  // Validation indicator icon
  const renderValidationIcon = () => {
    switch (validationState) {
      case 'validating':
        return (
          <svg className="w-3 h-3 animate-spin text-gray-400" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        );
      case 'valid':
        return (
          <svg className="w-3 h-3 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        );
      case 'will_create':
        return (
          <svg className="w-3 h-3 text-yellow-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" title="Directory will be created">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
        );
      case 'error':
        return (
          <svg className="w-3 h-3 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        );
      default:
        return null;
    }
  };

  // Editing mode
  if (isEditing) {
    return (
      <div ref={containerRef} className="flex items-center gap-1.5 relative">
        <input
          ref={inputRef}
          type="text"
          value={editValue}
          onChange={(e) => {
            setEditValue(e.target.value);
            setValidationState(null);
            setErrorMessage('');
          }}
          onKeyDown={handleKeyDown}
          className={`w-64 px-2 py-1 text-xs border rounded focus:outline-none focus:ring-1 ${
            validationState === 'error'
              ? 'border-red-300 focus:ring-red-300 bg-red-50'
              : 'border-gray-300 focus:ring-blue-300'
          }`}
          placeholder="Enter path"
        />

        {validationState && (
          <div className="flex items-center">
            {renderValidationIcon()}
          </div>
        )}

        <button
          onClick={handleConfirm}
          disabled={validationState === 'validating'}
          className="px-2 py-1 text-xs text-white bg-blue-500 hover:bg-blue-600 rounded disabled:opacity-50"
        >
          OK
        </button>

        <button
          onClick={handleCancel}
          className="text-xs text-gray-500 hover:text-gray-700"
        >
          Cancel
        </button>

        {validationState === 'error' && errorMessage && (
          <div className="absolute top-full left-0 mt-1 px-2 py-1.5 text-xs text-red-700 bg-red-100 border border-red-300 rounded shadow-md whitespace-nowrap z-10">
            <span className="font-medium">Error:</span> {errorMessage}
          </div>
        )}

        {validationState === 'will_create' && (
          <div className="absolute top-full left-0 mt-1 px-2 py-1 text-xs text-yellow-700 bg-yellow-50 border border-yellow-200 rounded shadow-sm whitespace-nowrap z-10">
            Directory will be created
          </div>
        )}
      </div>
    );
  }

  // Editable mode for new sessions
  if (isEditable && cwdInfo?.cwd) {
    const displayPath = cwdInfo.shortened || cwdInfo.cwd;
    return (
      <div
        className="flex items-center gap-1 min-w-0 cursor-pointer hover:bg-gray-100 rounded px-1.5 py-0.5 -mx-1.5"
        onClick={handleStartEdit}
        title={`Click to change working directory\n${cwdInfo.cwd}`}
      >
        <span className="text-xs truncate text-gray-500">
          {displayPath}
        </span>
        <svg className="w-2.5 h-2.5 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
        </svg>
      </div>
    );
  }

  // Read-only mode for existing sessions
  if (!isEditable && currentCwd) {
    // Shorten path for display (show last 2-3 segments)
    const segments = currentCwd.split('/').filter(Boolean);
    const shortened = segments.length > 3
      ? '.../' + segments.slice(-2).join('/')
      : currentCwd;

    return (
      <div
        className="flex items-center gap-1 min-w-0"
        title={currentCwd}
      >
        <span className="text-xs truncate text-gray-400">
          {shortened}
        </span>
      </div>
    );
  }

  return null;
}
