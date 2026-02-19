-- ======================================================================
-- citation_paths + citation_path_nodes
-- ======================================================================

INSERT INTO citation_paths (path_id, seed_paper_id, max_depth, path_score)
VALUES
  ('757c7f7e-1489-42ae-b6f9-f25182ed53b0',  '204e3073870fae3d05bcbc2f6a8e263d9b72e776', 2, NULL),
  ('669663b3-377d-4119-aadb-958df6587452', '204e3073870fae3d05bcbc2f6a8e263d9b72e776', 2, NULL)
ON CONFLICT (path_id) DO NOTHING;

INSERT INTO citation_path_nodes
  (path_id, paper_id, depth, position, is_influential, influence_reason)
VALUES
  ('757c7f7e-1489-42ae-b6f9-f25182ed53b0', '204e3073870fae3d05bcbc2f6a8e263d9b72e776', 0, 1, TRUE, 'Seed paper'),
  ('757c7f7e-1489-42ae-b6f9-f25182ed53b0', '2c03df8b48bf3fa39054345bafabfeff15bfd11d', 1, 2, FALSE, NULL),
  ('757c7f7e-1489-42ae-b6f9-f25182ed53b0', 'abd1c342495432171beb7ca8fd9551ef13cbd0ff', 2, 3, FALSE, NULL),
  ('757c7f7e-1489-42ae-b6f9-f25182ed53b0', 'eb42cf88027de515750f230b23b1a057dc782108', 2, 4, FALSE, NULL),
  ('757c7f7e-1489-42ae-b6f9-f25182ed53b0', 'bc6dff14a130c57a91d5a21339c23471faf1d46f', 2, 5, FALSE, NULL),
  ('757c7f7e-1489-42ae-b6f9-f25182ed53b0', 'a6cb366736791bcccc5c8639de5a8f9636bf87e8', 1, 6, FALSE, NULL),
  ('757c7f7e-1489-42ae-b6f9-f25182ed53b0', 'abd1c342495432171beb7ca8fd9551ef13cbd0ff', 2, 7, FALSE, NULL),
  ('757c7f7e-1489-42ae-b6f9-f25182ed53b0', '5f5dc5b9a2ba710937e2c413b37b053cd673df02', 2, 8, FALSE, NULL),
  ('757c7f7e-1489-42ae-b6f9-f25182ed53b0', '7c59908c946a4157abc030cdbe2b63d08ba97db3', 2, 9, FALSE, NULL),
  ('757c7f7e-1489-42ae-b6f9-f25182ed53b0', 'fa72afa9b2cbc8f0d7b05d52548906610ffbb9c5', 1, 10, FALSE, NULL),
  ('757c7f7e-1489-42ae-b6f9-f25182ed53b0', '2e9d221c206e9503ceb452302d68d10e293f2a10', 2, 11, FALSE, NULL),
  ('757c7f7e-1489-42ae-b6f9-f25182ed53b0', '0b544dfe355a5070b60986319a3f51fb45d1348e', 2, 12, FALSE, NULL),
  ('757c7f7e-1489-42ae-b6f9-f25182ed53b0', 'cea967b59209c6be22829699f05b8b1ac4dc092d', 2, 13, FALSE, NULL),
  ('669663b3-377d-4119-aadb-958df6587452', '204e3073870fae3d05bcbc2f6a8e263d9b72e776', 0, 1, TRUE, 'Seed paper'),
  ('669663b3-377d-4119-aadb-958df6587452', '5c126ae3421f05768d8edd97ecd44b1364e2c99a', 1, 2, FALSE, NULL),
  ('669663b3-377d-4119-aadb-958df6587452', 'c10075b3746a9f3dd5811970e93c8ca3ad39b39d', 2, 3, FALSE, NULL),
  ('669663b3-377d-4119-aadb-958df6587452', '64ea8f180d0682e6c18d1eb688afdb2027c02794', 2, 4, FALSE, NULL),
  ('669663b3-377d-4119-aadb-958df6587452', '9695824d7a01fad57ba9c01d7d76a519d78d65e7', 2, 5, FALSE, NULL),
  ('669663b3-377d-4119-aadb-958df6587452', '962dc29fdc3fbdc5930a10aba114050b82fe5a3e', 1, 6, FALSE, NULL),
  ('669663b3-377d-4119-aadb-958df6587452', 'e3d7778a47c6cab4ea1ef3ee9d19ec1510c15c60', 2, 7, FALSE, NULL),
  ('669663b3-377d-4119-aadb-958df6587452', '26218bdcc3945c7edae7aa2adbfba4cd820a2df3', 2, 8, FALSE, NULL),
  ('669663b3-377d-4119-aadb-958df6587452', '7a9a708ca61c14886aa0dcd6d13dac7879713f5f', 2, 9, FALSE, NULL),
  ('669663b3-377d-4119-aadb-958df6587452', '659bf9ce7175e1ec266ff54359e2bd76e0b7ff31', 1, 10, FALSE, NULL),
  ('669663b3-377d-4119-aadb-958df6587452', '46f9f7b8f88f72e12cbdb21e3311f995eb6e65c5', 2, 11, FALSE, NULL),
  ('669663b3-377d-4119-aadb-958df6587452', '8342b592fe238f3d230e4959b06fd10153c45db1', 2, 12, FALSE, NULL),
  ('669663b3-377d-4119-aadb-958df6587452', 'b3848d32f7294ec708627897833c4097eb4d8778', 2, 13, FALSE, NULL)
ON CONFLICT (path_id, paper_id) DO UPDATE SET
  depth            = EXCLUDED.depth,
  position         = EXCLUDED.position,
  is_influential   = EXCLUDED.is_influential,
  influence_reason = EXCLUDED.influence_reason,
  updated_at       = NOW();
