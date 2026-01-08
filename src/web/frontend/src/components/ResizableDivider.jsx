import { useState, useRef, useEffect } from 'react';

/**
 * Resizable divider component for adjusting split panel widths.
 *
 * Features:
 * - Drag to resize panels
 * - Hover to show hide buttons (with extended hover area and delay)
 * - Click left button to hide left panel
 * - Click right button to hide right panel
 */
export function ResizableDivider({ onResize, onHideLeft, onHideRight }) {
  const [isDragging, setIsDragging] = useState(false);
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
    // Add a delay before hiding buttons to give user time to move to them
    hideTimeoutRef.current = setTimeout(() => {
      setIsHovering(false);
    }, 200); // 200ms delay
  };

  const handleMouseDown = (e) => {
    e.preventDefault();
    setIsDragging(true);

    const startX = e.clientX;

    const handleMouseMove = (moveEvent) => {
      // Calculate percentage based on current mouse position
      const containerWidth = window.innerWidth;
      const mouseX = moveEvent.clientX;
      const newPercentage = (mouseX / containerWidth) * 100;

      // Constrain between 15% and 85%
      const constrainedPercentage = Math.min(Math.max(newPercentage, 15), 85);
      onResize(constrainedPercentage);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  return (
    // Outer container that includes divider + button zones
    // This ensures hover state is maintained when moving to buttons
    <div
      className="relative flex items-center justify-center"
      style={{ width: '100px' }} // Wide enough to cover buttons on both sides
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* The actual divider line */}
      <div
        className={`
          absolute left-1/2 -translate-x-1/2
          w-1 h-full bg-gray-200 hover:bg-blue-400 cursor-col-resize
          transition-colors duration-150
          ${isDragging ? 'bg-blue-500' : ''}
        `}
        onMouseDown={handleMouseDown}
      >
        {/* Drag indicator dots */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col gap-1 pointer-events-none">
          <div className="w-1 h-1 rounded-full bg-gray-400" />
          <div className="w-1 h-1 rounded-full bg-gray-400" />
          <div className="w-1 h-1 rounded-full bg-gray-400" />
        </div>
      </div>

      {/* Hide buttons - shown on hover with smooth transition */}
      {(isHovering || isDragging) && (
        <>
          {/* Left hide button */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onHideLeft();
            }}
            onMouseEnter={handleMouseEnter} // Keep visible when hovering button
            className="
              absolute left-0 top-1/2 -translate-y-1/2
              w-8 h-16 rounded-l-lg
              bg-blue-500 hover:bg-blue-600
              text-white shadow-lg
              flex items-center justify-center
              transition-all duration-150
              z-10
              group
            "
            title="Hide chat panel"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4 group-hover:scale-110 transition-transform"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z"
                clipRule="evenodd"
              />
            </svg>
          </button>

          {/* Right hide button */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onHideRight();
            }}
            onMouseEnter={handleMouseEnter} // Keep visible when hovering button
            className="
              absolute right-0 top-1/2 -translate-y-1/2
              w-8 h-16 rounded-r-lg
              bg-blue-500 hover:bg-blue-600
              text-white shadow-lg
              flex items-center justify-center
              transition-all duration-150
              z-10
              group
            "
            title="Hide plot panel"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4 group-hover:scale-110 transition-transform"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </>
      )}
    </div>
  );
}
