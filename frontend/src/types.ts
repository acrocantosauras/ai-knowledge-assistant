export interface User {
  id: string;
  email: string;
  display_name: string | null;
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface Document {
  id: string;
  title: string;
  source_type: string;
  content_type: string | null;
  status: string;
  checksum: string | null;
  document_metadata: Record<string, unknown>;
  content_excerpt: string;
  created_at: string;
  updated_at: string;
  chunk_count: number;
}

export interface DocumentListResponse {
  documents: Document[];
  total: number;
  limit: number;
  offset: number;
}

export interface Conversation {
  id: string;
  user_id: string;
  title: string | null;
  status: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  user_id: string;
  role: string;
  content: string;
  token_count: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ConversationWithMessages extends Conversation {
  messages: Message[];
}

export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
  limit: number;
  offset: number;
}

export interface QAResponse {
  answer: string;
  sources: Source[];
  provider: string;
  model: string;
  token_count: number | null;
  conversation_id: string;
  question_message_id: string;
  answer_message_id: string;
}

export interface Source {
  document_id: string;
  chunk_id: string;
  content_preview: string;
  score: number | null;
}

export interface RAGSearchResult {
  chunk_id: string;
  document_id: string;
  content: string;
  score: number | null;
  document_title: string | null;
  chunk_index: number | null;
}

export interface RAGSearchResponse {
  query: string;
  results: RAGSearchResult[];
  total: number;
}
