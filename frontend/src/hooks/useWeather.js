import { useState, useEffect } from 'react';

/**
 * Requests the user's geolocation and fetches current weather from OpenWeatherMap.
 * If the user denies location access, returns nulls silently.
 *
 * @returns {{ temp: number|null, description: string|null, city: string|null, icon: string|null, loading: boolean, error: string|null }}
 */
const useWeather = () => {
  const [weather, setWeather] = useState({
    temp: null,
    description: null,
    city: null,
    icon: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    if (!navigator.geolocation) {
      setWeather(prev => ({ ...prev, loading: false }));
      return;
    }

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const { latitude, longitude } = position.coords;
        const apiKey = import.meta.env.VITE_OPENWEATHER_API_KEY;

        if (!apiKey) {
          setWeather(prev => ({ ...prev, loading: false }));
          return;
        }

        try {
          const url = `https://api.openweathermap.org/data/2.5/weather?lat=${latitude}&lon=${longitude}&appid=${apiKey}&units=metric&lang=es`;
          const res = await fetch(url);
          if (!res.ok) throw new Error('Weather fetch failed');
          const data = await res.json();

          setWeather({
            temp: Math.round(data.main?.temp ?? null),
            description: data.weather?.[0]?.description ?? null,
            city: data.name ?? null,
            icon: data.weather?.[0]?.icon ?? null,
            loading: false,
            error: null,
          });
        } catch {
          // Silently fail — weather is non-critical
          setWeather(prev => ({ ...prev, loading: false }));
        }
      },
      () => {
        // User denied location — silent fallback
        setWeather({
          temp: null,
          description: null,
          city: null,
          icon: null,
          loading: false,
          error: null,
        });
      }
    );
  }, []);

  return weather;
};

export default useWeather;
