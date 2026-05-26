/**
 * Minimal hand-written Supabase database types.
 * Generated types (via `supabase gen types`) can replace this file later.
 */
export type Json = string | number | boolean | null | { [key: string]: Json } | Json[];

export type Database = {
  public: {
    Tables: {
      profiles: {
        Row: {
          id:            string;
          email:         string;
          name:          string | null;
          image_url:     string | null;
          signin_method: string | null;
          is_admin:      boolean;
          created_at:    string;
          last_seen_at:  string;
        };
        Insert: Partial<Database["public"]["Tables"]["profiles"]["Row"]> & { id: string; email: string };
        Update: Partial<Database["public"]["Tables"]["profiles"]["Row"]>;
      };
      saved_results: {
        Row: {
          id:            string;
          user_id:       string;
          name:          string;
          strategy_name: string | null;
          symbol:        string | null;
          timeframe:     string | null;
          bars:          number | null;
          metrics:       Json;
          equity_curve:  Json | null;
          graph:         Json | null;
          created_at:    string;
        };
        Insert: Omit<Database["public"]["Tables"]["saved_results"]["Row"], "id" | "created_at"> & { id?: string; created_at?: string };
        Update: Partial<Database["public"]["Tables"]["saved_results"]["Row"]>;
      };
      saved_strategies: {
        Row: {
          id:         string;
          user_id:    string;
          name:       string;
          graph:      Json;
          symbol:     string;
          timeframe:  string;
          created_at: string;
          updated_at: string;
        };
        Insert: Omit<Database["public"]["Tables"]["saved_strategies"]["Row"], "id" | "created_at" | "updated_at"> & { id?: string; created_at?: string; updated_at?: string };
        Update: Partial<Database["public"]["Tables"]["saved_strategies"]["Row"]>;
      };
      testimonials: {
        Row: {
          id:         string;
          user_id:    string | null;
          name:       string;
          role:       string | null;
          text:       string;
          tags:       string[];
          status:     string;
          avatar:     string | null;
          created_at: string;
        };
        Insert: Omit<Database["public"]["Tables"]["testimonials"]["Row"], "id" | "created_at"> & { id?: string; created_at?: string };
        Update: Partial<Database["public"]["Tables"]["testimonials"]["Row"]>;
      };
      broker_connections: {
        Row: {
          id:              string;
          user_id:         string;
          source_id:       string;
          label:           string | null;
          config:          Json;
          credentials_enc: string | null;
          is_active:       boolean;
          created_at:      string;
        };
        Insert: Omit<Database["public"]["Tables"]["broker_connections"]["Row"], "id" | "created_at"> & { id?: string; created_at?: string };
        Update: Partial<Database["public"]["Tables"]["broker_connections"]["Row"]>;
      };
    };
    Views:   Record<string, never>;
    Functions: Record<string, never>;
  };
};
