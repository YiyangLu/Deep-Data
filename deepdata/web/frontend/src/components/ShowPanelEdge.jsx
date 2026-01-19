import { useState, useRef, useEffect } from 'react';

/**
 * Edge component for showing hidden panels with hover interaction.
 *
 * Features:
 * - Thin edge zone (8px) that expands on hover
 * - Show button appears on hover with delay
 * - Consistent with ResizableDivider hide button pattern
 */
export function ShowPanelEdge({ side, onShow, panelName }) {
  const [isHovering, setIsHovering] = useState(false);
  const hideTimeoutRef = useRef(null);

  // Clean up timeout on unmount
  useEffect(() => {
    return () => {
      if (hideTimeoutRef.current) {
        clearTimeout(hideTimeoutRef.current);
      }
    };
  }, []);

  const handleMouseEnter = () => {
    // Clear any pending hide timeout
    if (hideTimeoutRef.current) {
      clearTimeout(hideTimeoutRef.current);
      hideTimeoutRef.current = null;
    }
    setIsHovering(true);
  };

  const handleMouseLeave = () => {
    // Add a delay before hiding button
    hideTimeoutRef.current = setTimeout(() => {
      setIsHovering(false);
    }, 200); // 200ms delay
  };

  // Determine icon rotation based on side
  const isLeft = side === 'left';
  const chevronPath = isLeft
    ? "M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" // Right chevron
    : "M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z"; // Left chevron

  return (
    <div
      className={`
        relative h-screen flex items-center justify-center
        transition-all duration-200
        ${isHovering ? 'w-20' : 'w-4'}
        ${isLeft ? 'bg-gradient-to-r from-gray-200' : 'bg-gradient-to-l from-gray-200'}
        to-transparent
        hover:from-blue-200
        cursor-pointer
        ${isLeft ? 'border-r-2' : 'border-l-2'}
        border-gray-300
      `}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={onShow}
      title={`Show ${panelName}`}
    >
      {/* Show button appears on hover */}
      {isHovering && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onShow();
          }}
          onMouseEnter={handleMouseEnter}
          className={`
            absolute top-1/2 -translate-y-1/2
            ${isLeft ? 'left-2' : 'right-2'}
            w-12 h-16
            ${isLeft ? 'rounded-lg' : 'rounded-lg'}
            bg-blue-500 hover:bg-blue-600
            text-white shadow-lg
            flex items-center justify-center
            transition-all duration-150
            z-10
            group
          `}
          title={`Show ${panelName}`}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-5 w-5 group-hover:scale-110 transition-transform"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fillRule="evenodd"
              d={chevronPath}
              clipRule="evenodd"
            />
          </svg>
        </button>
      )}

      {/* Subtle hint dots when not hovering */}
      {!isHovering && (
        <div className="absolute flex flex-col gap-1.5 pointer-events-none">
          <div className="w-1 h-1 rounded-full bg-gray-500" />
          <div className="w-1 h-1 rounded-full bg-gray-500" />
          <div className="w-1 h-1 rounded-full bg-gray-500" />
        </div>
      )}
    </div>
  );
}
