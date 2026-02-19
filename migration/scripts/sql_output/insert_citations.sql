-- ======================================================================
-- citations
-- ======================================================================

INSERT INTO citations (citing_paper_id, cited_paper_id, citation_context)
VALUES
  ('204e3073870fae3d05bcbc2f6a8e263d9b72e776', '2c03df8b48bf3fa39054345bafabfeff15bfd11d', 'methodology'),
  ('2c03df8b48bf3fa39054345bafabfeff15bfd11d', 'abd1c342495432171beb7ca8fd9551ef13cbd0ff', 'methodology, background'),
  ('2c03df8b48bf3fa39054345bafabfeff15bfd11d', 'eb42cf88027de515750f230b23b1a057dc782108', 'methodology, background'),
  ('2c03df8b48bf3fa39054345bafabfeff15bfd11d', 'bc6dff14a130c57a91d5a21339c23471faf1d46f', 'methodology, background'),
  ('204e3073870fae3d05bcbc2f6a8e263d9b72e776', 'a6cb366736791bcccc5c8639de5a8f9636bf87e8', 'methodology'),
  ('a6cb366736791bcccc5c8639de5a8f9636bf87e8', 'abd1c342495432171beb7ca8fd9551ef13cbd0ff', 'methodology'),
  ('a6cb366736791bcccc5c8639de5a8f9636bf87e8', '5f5dc5b9a2ba710937e2c413b37b053cd673df02', 'methodology, background'),
  ('a6cb366736791bcccc5c8639de5a8f9636bf87e8', '7c59908c946a4157abc030cdbe2b63d08ba97db3', 'methodology'),
  ('204e3073870fae3d05bcbc2f6a8e263d9b72e776', 'fa72afa9b2cbc8f0d7b05d52548906610ffbb9c5', 'background, methodology'),
  ('fa72afa9b2cbc8f0d7b05d52548906610ffbb9c5', '2e9d221c206e9503ceb452302d68d10e293f2a10', 'methodology'),
  ('fa72afa9b2cbc8f0d7b05d52548906610ffbb9c5', '0b544dfe355a5070b60986319a3f51fb45d1348e', 'methodology, background'),
  ('fa72afa9b2cbc8f0d7b05d52548906610ffbb9c5', 'cea967b59209c6be22829699f05b8b1ac4dc092d', 'methodology, background'),
  ('5c126ae3421f05768d8edd97ecd44b1364e2c99a', '204e3073870fae3d05bcbc2f6a8e263d9b72e776', 'methodology'),
  ('c10075b3746a9f3dd5811970e93c8ca3ad39b39d', '5c126ae3421f05768d8edd97ecd44b1364e2c99a', 'methodology, background'),
  ('64ea8f180d0682e6c18d1eb688afdb2027c02794', '5c126ae3421f05768d8edd97ecd44b1364e2c99a', 'methodology, background'),
  ('9695824d7a01fad57ba9c01d7d76a519d78d65e7', '5c126ae3421f05768d8edd97ecd44b1364e2c99a', 'methodology, background'),
  ('962dc29fdc3fbdc5930a10aba114050b82fe5a3e', '204e3073870fae3d05bcbc2f6a8e263d9b72e776', 'methodology, background'),
  ('e3d7778a47c6cab4ea1ef3ee9d19ec1510c15c60', '962dc29fdc3fbdc5930a10aba114050b82fe5a3e', 'methodology, background'),
  ('26218bdcc3945c7edae7aa2adbfba4cd820a2df3', '962dc29fdc3fbdc5930a10aba114050b82fe5a3e', 'methodology, background'),
  ('7a9a708ca61c14886aa0dcd6d13dac7879713f5f', '962dc29fdc3fbdc5930a10aba114050b82fe5a3e', 'methodology'),
  ('659bf9ce7175e1ec266ff54359e2bd76e0b7ff31', '204e3073870fae3d05bcbc2f6a8e263d9b72e776', 'methodology'),
  ('46f9f7b8f88f72e12cbdb21e3311f995eb6e65c5', '659bf9ce7175e1ec266ff54359e2bd76e0b7ff31', 'methodology, background'),
  ('8342b592fe238f3d230e4959b06fd10153c45db1', '659bf9ce7175e1ec266ff54359e2bd76e0b7ff31', 'methodology'),
  ('b3848d32f7294ec708627897833c4097eb4d8778', '659bf9ce7175e1ec266ff54359e2bd76e0b7ff31', 'methodology')
ON CONFLICT (citing_paper_id, cited_paper_id) DO UPDATE SET
  citation_context = EXCLUDED.citation_context,
  updated_at       = NOW();
