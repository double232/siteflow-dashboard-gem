/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import type { GraphResponse, SitesResponse, WebSocketMessage } from './types';
import { WebSocketClient } from './websocket';

interface WebSocketContextValue {
  isConnected: boolean;
  lastMessage: WebSocketMessage | null;
  startAction: (container: string, action: string) => void;
  subscribe: (topic: string) => void;
  unsubscribe: (topic: string) => void;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

interface WebSocketProviderProps {
  children: ReactNode;
}

export const WebSocketProvider = ({ children }: WebSocketProviderProps) => {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const clientRef = useRef<WebSocketClient | null>(null);
  const previousConnectionRef = useRef(false);
  const queryClient = useQueryClient();

  useEffect(() => {
    const client = new WebSocketClient();
    clientRef.current = client;

    const removeHandler = client.addHandler((message) => {
      setLastMessage(message);

      // Update React Query cache based on message type
      if (message.type === 'sites.update') {
        queryClient.setQueryData(['sites'], message.data as SitesResponse);
      } else if (message.type === 'graph.update') {
        queryClient.setQueryData(['graph'], message.data as GraphResponse);
      }
    });

    const removeStatus = client.addStatusHandler((connected) => {
      setIsConnected(connected);
      if (connected && !previousConnectionRef.current) {
        queryClient.invalidateQueries({ queryKey: ['sites'] });
        queryClient.invalidateQueries({ queryKey: ['graph'] });
      }
      previousConnectionRef.current = connected;
    });

    client.connect();

    return () => {
      removeHandler();
      removeStatus();
      client.disconnect();
    };
  }, [queryClient]);

  const startAction = useCallback((container: string, action: string) => {
    clientRef.current?.startAction(container, action);
  }, []);

  const subscribe = useCallback((topic: string) => {
    clientRef.current?.subscribe(topic);
  }, []);

  const unsubscribe = useCallback((topic: string) => {
    clientRef.current?.unsubscribe(topic);
  }, []);

  const value = useMemo(
    () => ({
      isConnected,
      lastMessage,
      startAction,
      subscribe,
      unsubscribe,
    }),
    [isConnected, lastMessage, startAction, subscribe, unsubscribe],
  );

  return (
    <WebSocketContext.Provider value={value}>{children}</WebSocketContext.Provider>
  );
};

export const useWebSocket = (): WebSocketContextValue => {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocket must be used within a WebSocketProvider');
  }
  return context;
};
