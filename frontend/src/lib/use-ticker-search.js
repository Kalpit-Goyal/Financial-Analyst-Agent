import { useEffect, useState } from "react";
import { api } from "./api";

/** Debounced company/ticker search backed by the /resolve endpoint. */
export function useTickerSearch(query) {
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      const trimmed = query.trim();
      if (trimmed.length < 2) {
        if (!cancelled) {
          setResults([]);
          setSearching(false);
        }
        return;
      }
      setSearching(true);
      try {
        const data = await api(`/resolve?q=${encodeURIComponent(trimmed)}`);
        if (!cancelled) {
          setResults(data.results || []);
          setError("");
        }
      } catch (err) {
        if (!cancelled) {
          setResults([]);
          setError(err.message);
        }
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, 350);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  return { results, searching, error };
}
