import { useState, useRef, useEffect } from 'react';

/**
 * Clean table-style path list.
 *
 * Shows example empty rows from the start. No borders, aligned text.
 * Enter to save, x to remove row.
 */
export function PathListField({
  paths,  // { key: path, ... }
  onChange,
  examples = []  // Array of { key: 'train', path: 'data/train.csv' }
}) {
  const [editingKey, setEditingKey] = useState(null);
  const [editName, setEditName] = useState('');
  const [editPath, setEditPath] = useState('');
  // Empty rows with example placeholders
  const [emptyRows, setEmptyRows] = useState(() =>
    examples.map((ex, i) => ({ id: i, name: '', path: '', keyPlaceholder: ex.key, pathPlaceholder: ex.path }))
  );
  const nameInputRef = useRef(null);

  const entries = Object.entries(paths || {});

  // Clear empty rows when paths are filled externally (e.g., auto-fill)
  useEffect(() => {
    if (entries.length > 0) {
      // Remove all empty rows that don't have user input
      setEmptyRows(prev => prev.filter(row => {
        const hasUserInput = row.name.trim() || row.path.trim();
        return hasUserInput;
      }));
    }
  }, [entries.length]);

  // Focus when editing starts
  useEffect(() => {
    if (editingKey && nameInputRef.current) {
      nameInputRef.current.focus();
    }
  }, [editingKey]);

  const handleStartEdit = (key, path) => {
    setEditingKey(key);
    setEditName(key);
    setEditPath(path);
  };

  const handleSaveEdit = () => {
    if (editName.trim() && editPath.trim()) {
      const newPaths = { ...paths };
      if (editingKey !== editName.trim()) {
        delete newPaths[editingKey];
      }
      newPaths[editName.trim()] = editPath.trim();
      onChange(newPaths);
    }
    setEditingKey(null);
    setEditName('');
    setEditPath('');
  };

  const handleCancelEdit = () => {
    setEditingKey(null);
    setEditName('');
    setEditPath('');
  };

  const handleDelete = (keyToDelete) => {
    const newPaths = { ...paths };
    delete newPaths[keyToDelete];
    onChange(newPaths);
  };

  const handleEditKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleSaveEdit();
    } else if (e.key === 'Escape') {
      handleCancelEdit();
    }
  };

  // Empty row management
  const updateEmptyRow = (id, field, value) => {
    setEmptyRows(prev => prev.map(row =>
      row.id === id ? { ...row, [field]: value } : row
    ));
  };

  const removeEmptyRow = (id) => {
    setEmptyRows(prev => prev.filter(row => row.id !== id));
  };

  const addEmptyRow = () => {
    const id = Date.now();
    setEmptyRows(prev => [...prev, { id, name: '', path: '', keyPlaceholder: 'name', pathPlaceholder: 'path/to/file' }]);
  };

  const handleEmptyRowKeyDown = (e, row) => {
    if (e.key === 'Enter' && row.name.trim() && row.path.trim()) {
      // Save this row
      const newPaths = { ...paths, [row.name.trim()]: row.path.trim() };
      onChange(newPaths);
      removeEmptyRow(row.id);
    } else if (e.key === 'Escape') {
      // Clear the row
      updateEmptyRow(row.id, 'name', '');
      updateEmptyRow(row.id, 'path', '');
    }
  };

  return (
    <div className="space-y-0.5">
      {/* Existing saved items */}
      {entries.map(([key, path]) => (
        editingKey === key ? (
          // Editing existing row
          <div key={key} className="flex items-center gap-3 py-1.5">
            <input
              ref={nameInputRef}
              type="text"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              onKeyDown={handleEditKeyDown}
              onBlur={handleSaveEdit}
              className="text-sm w-28 text-gray-700 font-medium bg-transparent border-b border-gray-300 focus:border-green-500 focus:outline-none"
            />
            <input
              type="text"
              value={editPath}
              onChange={(e) => setEditPath(e.target.value)}
              onKeyDown={handleEditKeyDown}
              onBlur={handleSaveEdit}
              className="text-sm flex-1 text-gray-500 font-mono bg-transparent border-b border-gray-300 focus:border-green-500 focus:outline-none"
            />
            <button
              onClick={handleCancelEdit}
              className="p-0.5 text-gray-300 hover:text-gray-500 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        ) : (
          // Display row
          <div
            key={key}
            className="group flex items-center gap-3 py-1.5 cursor-pointer hover:bg-gray-50 -mx-2 px-2 rounded"
            onClick={() => handleStartEdit(key, path)}
          >
            <span className="text-sm font-medium text-gray-700 w-28 truncate" title={key}>
              {key}
            </span>
            <span className="text-sm text-gray-500 flex-1 truncate font-mono" title={path}>
              {path}
            </span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleDelete(key);
              }}
              className="p-0.5 text-gray-300 opacity-0 group-hover:opacity-100 hover:text-gray-500 transition-all"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )
      ))}

      {/* Empty rows with example placeholders */}
      {emptyRows.map((row) => (
        <div key={row.id} className="flex items-center gap-3 py-1.5">
          <input
            type="text"
            value={row.name}
            onChange={(e) => updateEmptyRow(row.id, 'name', e.target.value)}
            onKeyDown={(e) => handleEmptyRowKeyDown(e, row)}
            placeholder={row.keyPlaceholder}
            className="text-sm w-28 text-gray-700 font-medium bg-transparent border-b border-gray-200 focus:border-green-500 focus:outline-none placeholder-gray-300"
          />
          <input
            type="text"
            value={row.path}
            onChange={(e) => updateEmptyRow(row.id, 'path', e.target.value)}
            onKeyDown={(e) => handleEmptyRowKeyDown(e, row)}
            placeholder={row.pathPlaceholder}
            className="text-sm flex-1 text-gray-500 font-mono bg-transparent border-b border-gray-200 focus:border-green-500 focus:outline-none placeholder-gray-300"
          />
          <button
            onClick={() => removeEmptyRow(row.id)}
            className="p-0.5 text-gray-300 hover:text-gray-500 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      ))}

      {/* "+ Add new path..." */}
      <div
        onClick={addEmptyRow}
        className="flex items-center gap-2 py-1.5 text-sm text-gray-400 hover:text-green-600 cursor-pointer transition-colors"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
        <span>Add new path...</span>
      </div>
    </div>
  );
}
