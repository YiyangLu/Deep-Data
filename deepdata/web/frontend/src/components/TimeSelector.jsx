import { useState, useRef, useEffect } from 'react';

const TIME_UNITS = [
  { value: 'min', label: 'm', fullLabel: 'min' },
  { value: 'hour', label: 'h', fullLabel: 'hour' },
  { value: 'day', label: 'd', fullLabel: 'day' },
];

/**
 * Minimalist time selector with inline editing.
 *
 * - Default: Shows "6h" as clickable text
 * - Editing: Inline number input + unit selector
 * - Number can be typed directly or adjusted with scroll/drag
 * - Unit cycles on click with subtle indicator
 *
 * @param {number} value - Time value in the selected unit
 * @param {string} unit - Time unit ('min', 'hour', 'day')
 * @param {function} onChange - Callback with (value, unit)
 * @param {string} theme - Color theme: 'green' (default) or 'purple'
 * @param {string} dropdownPosition - Dropdown position: 'top' (default) or 'bottom'
 */
export function TimeSelector({ value, unit, onChange, theme = 'green', dropdownPosition = 'top' }) {
  const [isEditing, setIsEditing] = useState(false);
  const [showUnitMenu, setShowUnitMenu] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });
  const containerRef = useRef(null);
  const inputRef = useRef(null);
  const unitRef = useRef(null);

  // Theme colors
  const colors = theme === 'purple' ? {
    text: 'text-purple-600',
    textMuted: 'text-purple-400',
    hoverBg: 'hover:bg-purple-50',
    activeBg: 'bg-purple-600',
    border: 'border-purple-200',
    ring: 'focus:ring-purple-400',
  } : {
    text: 'text-gray-600',
    textMuted: 'text-gray-400',
    hoverBg: 'hover:bg-green-50',
    activeBg: 'bg-green-600',
    border: 'border-gray-200',
    ring: 'focus:ring-green-400',
  };

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setIsEditing(false);
        setShowUnitMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Focus input when entering edit mode
  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  // Close unit menu on click outside (but within container)
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (unitRef.current && !unitRef.current.contains(e.target)) {
        setShowUnitMenu(false);
      }
    };
    if (showUnitMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showUnitMenu]);

  // Get unit display
  const unitData = TIME_UNITS.find(u => u.value === unit) || TIME_UNITS[1];
  const unitLabel = unitData.label;

  // Handle number input change
  const handleValueChange = (e) => {
    const newValue = parseInt(e.target.value) || 1;
    onChange(Math.max(1, newValue), unit);
  };

  // Handle wheel on number to increase/decrease
  const handleWheel = (e) => {
    if (!isEditing) return;
    e.preventDefault();
    const delta = e.deltaY < 0 ? 1 : -1;
    onChange(Math.max(1, value + delta), unit);
  };

  // Cycle to next unit
  const cycleUnit = () => {
    const currentIndex = TIME_UNITS.findIndex(u => u.value === unit);
    const nextIndex = (currentIndex + 1) % TIME_UNITS.length;
    onChange(value, TIME_UNITS[nextIndex].value);
  };

  // Handle key events
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === 'Escape') {
      setIsEditing(false);
      setShowUnitMenu(false);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      onChange(value + 1, unit);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      onChange(Math.max(1, value - 1), unit);
    }
  };

  // Compact display mode (not editing)
  if (!isEditing) {
    return (
      <button
        ref={containerRef}
        onClick={() => setIsEditing(true)}
        className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded text-sm font-medium transition-colors ${colors.text} ${colors.hoverBg} cursor-pointer`}
        title="Click to edit duration"
      >
        <svg className="w-3.5 h-3.5 opacity-60" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span>{value}{unitLabel}</span>
      </button>
    );
  }

  // Edit mode - inline input with unit selector
  return (
    <div ref={containerRef} className="flex items-center">
      {/* Number input - minimal style */}
      <input
        ref={inputRef}
        type="number"
        value={value}
        onChange={handleValueChange}
        onKeyDown={handleKeyDown}
        onWheel={handleWheel}
        className={`w-10 px-1 py-0.5 text-sm font-medium text-center border-b-2 ${colors.border} bg-transparent focus:outline-none focus:border-current ${colors.text} [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none`}
        min="1"
      />

      {/* Unit selector - click to show menu */}
      <div className="relative" ref={unitRef}>
        <button
          onClick={() => {
            if (!showUnitMenu && unitRef.current) {
              const rect = unitRef.current.getBoundingClientRect();
              const topPos = dropdownPosition === 'bottom'
                ? rect.bottom + 4
                : rect.top - 85;
              setMenuPosition({ top: topPos, left: rect.left });
            }
            setShowUnitMenu(!showUnitMenu);
          }}
          className={`flex items-center gap-0.5 px-1 py-0.5 text-sm font-medium ${colors.text} hover:opacity-80 transition-opacity`}
          title="Click to change unit"
        >
          <span>{unitLabel}</span>
          <svg className={`w-2.5 h-2.5 opacity-50 transition-transform ${showUnitMenu ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {/* Unit dropdown - fixed position to escape overflow container */}
        {showUnitMenu && (
          <div className="fixed bg-white border border-gray-200 rounded shadow-lg py-1 min-w-[60px] z-50"
               style={{ top: menuPosition.top, left: menuPosition.left }}>
            {TIME_UNITS.map((u) => (
              <button
                key={u.value}
                onClick={() => {
                  onChange(value, u.value);
                  setShowUnitMenu(false);
                }}
                className={`w-full px-3 py-1 text-sm text-left hover:bg-gray-100 transition-colors ${
                  unit === u.value ? `${colors.text} font-medium` : 'text-gray-600'
                }`}
              >
                {u.fullLabel}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Convert time value and unit to seconds.
 */
export function timeToSeconds(value, unit) {
  const multipliers = { min: 60, hour: 3600, day: 86400 };
  return value * (multipliers[unit] || 3600);
}

/**
 * Convert seconds to value and unit (picks best unit).
 */
export function secondsToTime(seconds) {
  const minutes = seconds / 60;
  if (minutes >= 1440 && minutes % 1440 === 0) {
    return { value: minutes / 1440, unit: 'day' };
  } else if (minutes >= 60 && minutes % 60 === 0) {
    return { value: minutes / 60, unit: 'hour' };
  }
  return { value: minutes, unit: 'min' };
}

/**
 * Convert minutes to value and unit (picks best unit).
 */
export function minutesToTime(minutes) {
  if (minutes >= 1440 && minutes % 1440 === 0) {
    return { value: minutes / 1440, unit: 'day' };
  } else if (minutes >= 60 && minutes % 60 === 0) {
    return { value: minutes / 60, unit: 'hour' };
  }
  return { value: minutes, unit: 'min' };
}
