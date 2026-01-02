import React, { useState, useEffect } from 'react';

export default function TickerNotes({ ticker }) {
    const [notes, setNotes] = useState([]);
    const [loading, setLoading] = useState(false);
    const [newNote, setNewNote] = useState('');
    const [editingNote, setEditingNote] = useState(null);
    const [editContent, setEditContent] = useState('');

    useEffect(() => {
        if (ticker) {
            fetchNotes();
        }
    }, [ticker]);

    const fetchNotes = async () => {
        setLoading(true);
        try {
            const response = await fetch(`/api/tickers/${ticker}/notes`);
            if (response.ok) {
                const data = await response.json();
                setNotes(data);
            }
        } catch (error) {
            console.error('Error fetching notes:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleAddNote = async (e) => {
        e.preventDefault();
        if (!newNote.trim()) return;

        try {
            const response = await fetch(`/api/tickers/${ticker}/notes`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: newNote })
            });

            if (response.ok) {
                const addedNote = await response.json();
                setNotes([addedNote, ...notes]);
                setNewNote('');
            }
        } catch (error) {
            console.error('Error adding note:', error);
        }
    };

    const handleDeleteNote = async (noteId) => {
        if (!confirm('Czy na pewno chcesz usunąć tę notatkę?')) return;

        try {
            const response = await fetch(`/api/notes/${noteId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                setNotes(notes.filter(n => n.id !== noteId));
            }
        } catch (error) {
            console.error('Error deleting note:', error);
        }
    };

    const startEditing = (note) => {
        setEditingNote(note.id);
        setEditContent(note.content);
    };

    const cancelEditing = () => {
        setEditingNote(null);
        setEditContent('');
    };

    const handleUpdateNote = async (noteId) => {
        if (!editContent.trim()) return;

        try {
            const response = await fetch(`/api/notes/${noteId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: editContent })
            });

            if (response.ok) {
                setNotes(notes.map(n => n.id === noteId ? { ...n, content: editContent, updated_at: new Date().toISOString() } : n));
                setEditingNote(null);
                setEditContent('');
            }
        } catch (error) {
            console.error('Error updating note:', error);
        }
    };

    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 mt-4">
            <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-4">Notatki</h3>
            
            <form onSubmit={handleAddNote} className="mb-4">
                <div className="flex gap-2">
                    <textarea
                        value={newNote}
                        onChange={(e) => setNewNote(e.target.value)}
                        placeholder="Dodaj nową notatkę..."
                        className="flex-1 min-h-[60px] p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm resize-y"
                    />
                    <button
                        type="submit"
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors self-start"
                    >
                        Dodaj
                    </button>
                </div>
            </form>

            <div className="space-y-3">
                {loading ? (
                    <p className="text-sm text-gray-500">Ładowanie notatek...</p>
                ) : notes.length === 0 ? (
                    <p className="text-sm text-gray-500 italic">Brak notatek dla tego tickera.</p>
                ) : (
                    notes.map(note => (
                        <div key={note.id} className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-gray-50 dark:bg-gray-900/30">
                            {editingNote === note.id ? (
                                <div className="space-y-2">
                                    <textarea
                                        value={editContent}
                                        onChange={(e) => setEditContent(e.target.value)}
                                        className="w-full min-h-[60px] p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                                    />
                                    <div className="flex justify-end gap-2">
                                        <button onClick={cancelEditing} className="px-3 py-1 text-xs bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600">Anuluj</button>
                                        <button onClick={() => handleUpdateNote(note.id)} className="px-3 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700">Zapisz</button>
                                    </div>
                                </div>
                            ) : (
                                <>
                                    <div className="flex justify-between items-start mb-2">
                                        <span className="text-xs text-gray-500 dark:text-gray-400">
                                            {note.created_at}
                                        </span>
                                        <div className="flex gap-2">
                                            <button onClick={() => startEditing(note)} className="text-blue-600 dark:text-blue-400 hover:underline text-xs">Edytuj</button>
                                            <button onClick={() => handleDeleteNote(note.id)} className="text-red-600 dark:text-red-400 hover:underline text-xs">Usuń</button>
                                        </div>
                                    </div>
                                    <p className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">{note.content}</p>
                                </>
                            )}
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}
