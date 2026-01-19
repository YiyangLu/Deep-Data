import { useState, useRef, useEffect } from 'react';

/**
 * Click-to-edit text field with slide-in note view.
 *
 * Shows preview, click to slide into full-width note editor.
 * Auto-saves on back.
 */
export function ClickToEditField({
  label,
  value,
  onChange,
  placeholder = 'Click to write...',
  maxPreviewLength = 80,
  multiline = false
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(value);
  const [isAnimating, setIsAnimating] = useState(false);
  const textareaRef = useRef(null);

  // Sync edit value when prop changes (and not editing)
  useEffect(() => {
    if (!isEditing) {
      setEditValue(value);
    }
  }, [value, isEditing]);

  // Focus and move cursor to end when editing starts
  useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.focus();
      const len = textareaRef.current.value.length;
      textareaRef.current.setSelectionRange(len, len);
    }
  }, [isEditing]);

  const handleOpen = () => {
    setIsAnimating(true);
    setIsEditing(true);
  };

  const handleBack = () => {
    // Auto-save on back
    onChange(editValue);
    setIsAnimating(false);
    // Wait for animation to complete before hiding
    setTimeout(() => setIsEditing(false), 200);
  };

  // Truncate for preview
  const getPreview = () => {
    if (!value) return null;
    if (value.length <= maxPreviewLength) return value;
    return value.slice(0, maxPreviewLength) + '...';
  };

  const isEmpty = !value || value.trim() === '';

  return (
    <>
      {/* Preview (click to edit) */}
      <div
        onClick={handleOpen}
        className={`relative cursor-pointer transition-all group ${
          isEmpty
            ? 'py-2 text-sm text-gray-400 hover:text-gray-500'
            : 'bg-gray-50 rounded-lg p-4 hover:bg-gray-100'
        }`}
      >
        {isEmpty ? (
          <span className="flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            {placeholder}
          </span>
        ) : (
          <>
            <div className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed line-clamp-3">
              {multiline ? value : getPreview()}
            </div>
            {/* Edit hint on hover */}
            <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            </div>
          </>
        )}
      </div>

      {/* Slide-in Note View */}
      {isEditing && (
        <div
          className={`fixed inset-0 z-50 bg-white flex flex-col transition-transform duration-200 ease-out ${
            isAnimating ? 'translate-x-0' : 'translate-x-full'
          }`}
        >
          {/* Header */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100">
            <button
              onClick={handleBack}
              className="p-1.5 -ml-1.5 rounded-lg text-gray-600 hover:text-gray-900 hover:bg-gray-100 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <span className="text-base font-medium text-gray-900">{label}</span>
          </div>

          {/* Editor - full height textarea */}
          <div className="flex-1 p-6 overflow-hidden">
            <textarea
              ref={textareaRef}
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              placeholder={placeholder}
              className="w-full h-full text-base leading-relaxed text-gray-800 placeholder-gray-400 resize-none focus:outline-none"
            />
          </div>
        </div>
      )}
    </>
  );
}
