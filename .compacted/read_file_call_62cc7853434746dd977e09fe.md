   185	    import sqlite3
   186	
   187	    conn = sqlite3.connect(":memory:")
   188	    conn.row_factory = sqlite3.Row
   189	    conn.execute(
   190	        "CREATE TABLE chunks_fts (chunk_id, project_id, entity_id, document_type, "
   191	        "title, summary, text, active) USING fts5("
   192	        "chunk_id UNINDEXED, project_id UNINDEXED, entity_id UNINDEXED, "
   193	        "document_type UNINDEXED, title, summary, text, active UNINDEXED, "
   194	        "tokenize = 'unicode61')"
   195	    )
   196	    conn.commit()
   197	    yield conn
   198	    conn.close()
   199	
   200	
   201	class TestLexicalIndex:
   202	    def test_upsert_and_search(self, sync_conn):
   203	        lex = LexicalIndex(sync_conn)
   204	        lex.upsert_chunk(
   205	            chunk_id="c1",