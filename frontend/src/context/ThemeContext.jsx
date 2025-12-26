import React, { createContext, useContext, useState, useEffect } from 'react';

const ThemeContext = createContext();

export const ThemeProvider = ({ children }) => {
    const [theme, setTheme] = useState(() => {
        const storedTheme = localStorage.getItem('theme');
        if (storedTheme) {
            return storedTheme;
        }
        // Initial fallback, will be updated by useEffect if not in localStorage
        return 'dark'; 
    });

    useEffect(() => {
        const fetchConfig = async () => {
            if (localStorage.getItem('theme')) return; // Don't override user preference

            try {
                const res = await fetch('/api/config');
                const data = await res.json();
                if (data.default_theme) {
                    setTheme(data.default_theme);
                }
            } catch (e) {
                console.error("Failed to fetch theme config:", e);
                // Fallback to system preference if API fails
                if (!localStorage.getItem('theme')) {
                    const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
                    setTheme(systemTheme);
                }
            }
        };
        fetchConfig();
    }, []);

    useEffect(() => {
        const root = window.document.documentElement;
        root.classList.remove('light', 'dark');
        root.classList.add(theme);
        localStorage.setItem('theme', theme);
        
        // Update body background color to match theme for better transitions
        if (theme === 'dark') {
            document.body.style.backgroundColor = '#111827'; // gray-900
        } else {
            document.body.style.backgroundColor = '#ffffff'; // white
        }
    }, [theme]);

    const toggleTheme = () => {
        setTheme((prevTheme) => (prevTheme === 'light' ? 'dark' : 'light'));
    };

    return (
        <ThemeContext.Provider value={{ theme, toggleTheme }}>
            {children}
        </ThemeContext.Provider>
    );
};

export const useTheme = () => useContext(ThemeContext);
