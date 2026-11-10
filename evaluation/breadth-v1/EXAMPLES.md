# Benign breadth examples

See [qualitative review notes](REVIEW.md) for selected examples, including remaining code-quality issues.

Every linked file is an unchanged, checksum-verified accepted artifact from an explicitly benign run. “Verified” means it passed the frozen task checks; it is not an all-input correctness or code-quality guarantee. “Review issue” means generic CLI acceptance succeeded but the independent task grade failed.

The primary study used the original frozen extraction behavior. Corrected extraction examples are separate in `supplement/extraction-audit/sources/` inside the reproduction archive.

| Format | Model | Task | Independent result | Source SHA-256 |
| --- | --- | --- | --- | --- |
| binary-info | deepseek | [binary-info-clr](candidates/e4e87b93df59d193afa02663f6f96054e771f95038b75e202a3d2b1e249de88f.txt) | Verified | `bfb48643181abea4e86d777d61ee7614bf632987849e4f2a9ce49849e5fb30c2` |
| binary-info | glm | [binary-info-clr](candidates/f0bebf3f303a481938c7de0b538d84f6fb875c02c291e7ec1ff2bc4210e9d4ac.txt) | Verified | `bfee37fcefb2b7ae95c1acc56b4dc2e873a88daf3d7c64b4f429c6d605badf69` |
| binary-info | deepseek | [binary-info-elf](candidates/d5b257162d024eb91790710f1e9bc4c7bedf3056f37882f60582425bab96e7b5.txt) | Verified | `d2b726fcfca0d2e8ac65c4677a36e0ba5c920e98bb8044c8556ecc1bd7a46bce` |
| binary-info | glm | [binary-info-elf](candidates/c7331b1ed7859c83fcf68f9ccd0a4aadf281eec2b8a1445bda2c2b8997779768.txt) | Verified | `bd111b48598095bf07af50f4df7daa26e2363a44b343a86ca5bd399336e5862f` |
| binary-info | deepseek | [binary-info-jvm](candidates/25385b212f0cfd9444c7d1928dfb73309176aff0f368d80489ca40fa22df7397.txt) | Verified | `39509a06b2177d73ec635fc0e46fd8206aeb0430ea8bb01ac6a5b8e4980041c9` |
| binary-info | glm | [binary-info-jvm](candidates/8fd3796c044a9b3ef054e249a4db163e9c86a6c42590ca4caa3d224c4afe23d7.txt) | Verified | `4ecfd2c2ddd9af2a76a45615bb9ae00f5a4a7ee9fcb97dc9096d645f6d175b3d` |
| binary-info | deepseek | [binary-info-mach-o](candidates/6aca4a46d1bdbc96279793c67bd6cc57f6ca029b5afb2d2c3e279ac176592dc2.txt) | Verified | `d4677ffa9254a0054e95a4faca0a4829dfe557463c1f7a4e89e73240829d57bf` |
| binary-info | glm | [binary-info-mach-o](candidates/1e4d0c827e45b8c0322bde456994c53c98ccf38d11f5d01f571b1a687ee1fba5.txt) | Verified | `efa1f49f5692d2a7aa9487c9fdd34d2971117f4adfb0560932b3e8f1afa82347` |
| binary-info | deepseek | [binary-info-pe](candidates/4f3b3ae3da112abe503124e88de91c2b509bb37e394d3f631e4c59ce124f37c2.txt) | Verified | `1557ff4dda51311fffe458ba6c1860c6ab8ca42caa94b0722b9218d0014e325d` |
| binary-info | glm | [binary-info-pe](candidates/4c67272499a33ba7c7fa8e73340c1274c8081127d23d2788bd8abcbd45037caa.txt) | Verified | `cc7f2e8fdce893e8fbdf497976dd52fcb15678289788d1966406916b1e1b45b2` |
| binary-info | deepseek | [binary-info-wasm](candidates/a1feee95ffc631d8680e86a75bfd1a8b178719732d6f901830c4966a773ad205.txt) | Verified | `387bd0d219dccb89f28e4a750f58c6063f21814db65e06966fffde500ab94366` |
| binary-info | glm | [binary-info-wasm](candidates/3ff73c81993f79b9b3fb15960d43a25959f9269842e926b4efc9a947f782515f.txt) | Verified | `941b8d5d4d8bb1b8a78eb13573eea7c27b516db51cc974954ea4e6d30c5d7893` |
| c | deepseek | [c-ceil_div](candidates/c61001edd85c6f49578b3a7fa232805ae7c6a89b3407fb7ff2392b180d3cbe69.txt) | Verified | `1f4451f039acd1c2e60f8556c58d0ef94d60b0d25fcdcaa487f9fc4fdf4230de` |
| c | glm | [c-ceil_div](candidates/d71685af26c7b1dea53eeecc349dee5521fdf0ac1ba99b3445ba960096f69cbe.txt) | Verified | `d9ce07c8ec7910fcb11349ec1239f82eb711643207843161edfc4a9b71476d62` |
| c | deepseek | [c-longest_run](candidates/9664b161f799d7060e997c50edf381b616408e5522f3d009a219282f89c5a2e9.txt) | Verified | `0cd7729950c7ebb4e5b8cb07c7d671438bce11e0dfb2458935036ea5e40154fb` |
| cpp | deepseek | [cpp-ceil_div](candidates/29456e8c347ceda0908c444955b898c0a44128608eed37ba1c2cfb0d6f85fc92.txt) | Verified | `c52775e434afdb4fb3804e93d7d69d6b5da40f715b3b128cbc121a39b31a01b5` |
| cpp | glm | [cpp-ceil_div](candidates/403535ba4f5135face97fba7269203aab494eda8db963660a243a007819bc211.txt) | Verified | `c3e9e318768b6f250d4981dc9eb480e4a9c5028e94d9c2426c9602a49d08de30` |
| cpp | deepseek | [cpp-longest_run](candidates/b7296aaa82631f30a9fe4cf8d1a8347a841ed8a9111e8603c4d2c00212decbb8.txt) | Verified | `0a2814736c0e1512ff20f768c49e912ad1146f793bc712879f05760f9b2c3859` |
| csv | deepseek | [csv-invoice](candidates/fb314ab958d37e1872f0b7a87097cf16b7ed77d7227047ea18d6730d4e7a1428.txt) | Review issue | `1d951a338692298500d783a0e7e7d17c860408273e206a7e0e149fa05d118f9a` |
| csv | deepseek | [csv-schedule](candidates/ed48f13f5bc57499087b72461d58c6eca0cd6bd52bfa0e2d3522c2eac75c94d0.txt) | Review issue | `92b89bc121105613b7d4a4310828090b72a4c95e9518036bd71f6d6c578e763c` |
| csv | deepseek | [csv-temperature](candidates/5ced446309f24e63ed4837051ce079b995de0d7a28fec989f5dc17d33547dfa0.txt) | Verified | `e704fcdb69a2a1c06d9443491fbfddc3f77342458343b79487eb79f043b538c5` |
| go | glm | [go-ceil_div](candidates/ec79959a7ae61ce050f1f4e0a98ae121421f71ce6fdd9adcf5188d53499f640f.txt) | Review issue | `a74194d495e6279c76e28fe086b638308b8d5dbe3da6090c3ceb7c366c45ff09` |
| html | deepseek | [html-invoice](candidates/dbfc6f3fc7c0783ca4287d9f64d3af9a38e0785652f8a2dece107e4c7798e4f9.txt) | Review issue | `65305e34bac230f483740990ee257450c9b3c955ab2402c341fd70cb00257095` |
| html | glm | [html-invoice](candidates/0790fcdf80e5d67785a7d9f3e4bdc24169204f513544d7df1b5499ebb9aaba4d.txt) | Review issue | `f4537ddd677314e29ed649c27afe3c6a8fcdad8653a908c9ded3ed24920d59bf` |
| html | deepseek | [html-schedule](candidates/999d3278c82729b8e880eeda3a6bb8b2a58d1fad1d6262695583172519eed179.txt) | Review issue | `45051bd07cbd36b753a7c300b25807e9f11de7e12565c4f0770afbdc2b5c27ad` |
| html | glm | [html-schedule](candidates/efadee526b49d8131b5d5e99352c4e5e1ed46634c00cb9b69a9e0a1ce60788e0.txt) | Review issue | `c36c10d9552693a7b17cb717193501315027c10ef6f20148e1e693e52aa94eeb` |
| html | deepseek | [html-temperature](candidates/2cfc74478063d8a193d5d158c2f57d1d65aab5b361f2e2acc7c622ea35234b7c.txt) | Verified | `42344a861453e1f6a954d6bbe848d7140a0818ecee6eb97e9c6e310be45f072d` |
| html | glm | [html-temperature](candidates/bce266a4ae78dcf085a1bdbf919c2aaaf58abc3d3d71332ec34f3e2194e42732.txt) | Review issue | `27b525c83eabb0b5b3c0ceb20c84331d9340168cadb6648036fefe2964efcfe5` |
| http | deepseek | [http-invoice](candidates/2ba18666394bd9f98ff1aec0b1f0d1ddadf4467ec43bcd097849d934dc67b828.txt) | Review issue | `15b9584a2954edeb93a863f8b482199bcee81ba8eaf9bc4538ae62bfd437a8aa` |
| http | deepseek | [http-schedule](candidates/8fd3952bd0d3212784b9ca803c21406ef1f703c485ac633f1a93602e915e2270.txt) | Verified | `09e5b73cda6ae2dca65f1de83e32503e0996e725ed469e19823644a0e2bdce17` |
| http | deepseek | [http-temperature](candidates/192cbda9322d026f74ec450ee6f2b5765fc06c628949bdfef8b2232af548d6be.txt) | Verified | `e95dd8f96f787985900e1fbf77dac1445d0c6e1508260c5dcb57dbf85c9f3cea` |
| ini | deepseek | [ini-invoice](candidates/e34693837280d5e7bca3ce41e6f340fe265422e5581e08134c4b7471f88fddc3.txt) | Review issue | `00f6d7787fda6ca07cb914e5fbf4bdc969b24b3bb6001cbe12aaa2ef9067511c` |
| ini | glm | [ini-invoice](candidates/a50174537e00415413a77009863380bc9bd66c2406ea329977403b181695ba30.txt) | Review issue | `f0de6c5ff8781cf4afe90c8ff48f7f7ce6a6596026bf3733d38e091e8c3d7cd5` |
| ini | deepseek | [ini-schedule](candidates/e865e0f2962ee2c7a46e6f2f98b8b398914a0d96df0c2976b604124a97eec4a4.txt) | Verified | `9da50898366ffe8b2e24255ed8ed85b94e7a213eabbf9050ab47dad32cdc37e5` |
| ini | glm | [ini-schedule](candidates/2876c952ea9574f427529ead7ce7f6cd3ca230e011dc87a1f243c732948d70a8.txt) | Review issue | `20fe680fc94a59455416c07b51936beab8201937d2d1e02a02f99007059e9bf5` |
| ini | deepseek | [ini-temperature](candidates/388815730d9b18805c2c33bfca43f06bce08d8cec75f494257cd9298ec7518a6.txt) | Verified | `28c9ce928115e592dcb9744de0cdebd39a63478ca5847132f18f44340d97660b` |
| ini | glm | [ini-temperature](candidates/2301f989dcaaaa3e53b5f4ef9b907b5fdcde1881d7e616792d404cff1ed72f2e.txt) | Verified | `13577b59a840daf7766866155b4d3a418208e7dd308d7aa3c088a2823d632948` |
| java | deepseek | [java-ceil_div](candidates/cca40b6df8cde4d466dd8e58fb259ab056009ac1f86975ccddec6e74b53df2d4.txt) | Verified | `7f727633b3875d2d9d5a12cfb7ae35337a91f2e09c842bb5f98c218008f5ac1e` |
| java | glm | [java-ceil_div](candidates/76aa3063ae8b611a7564e518e66e71cec938f8d17143db70a962e73c6a2de8f8.txt) | Verified | `249444dc8d8f955e9a4783d6b9f983e6fff129f6cc94a7c2559b50c4a1fe214d` |
| java | deepseek | [java-longest_run](candidates/3b8fdc125727c57fac465644064546f5951cb5b69a658559ee0a6897ceb5c6f4.txt) | Verified | `04db118464caec057ff72a6b88fe294e2c9b926ed66cc52ad5f2968e60b65ba7` |
| java | glm | [java-longest_run](candidates/6cd7cbdb8d140757d1d79e5f6adac06e34ee6283f7f188a4526172a6acd0c2a0.txt) | Review issue | `eff8f8b4568f10e53cd4602c70db15999082e1ebc66e5b9f3c4cb39cf5ba885d` |
| javascript | deepseek | [javascript-ceil_div](candidates/3df9f1f39f3d4c61e225f41ac5a2076fbde0d686d49fa456ef3699799ae7339a.txt) | Verified | `34af7b436cb7d261416d1308b35b27aaa7a0205746f1d1065a5e2715fd687da5` |
| javascript | glm | [javascript-ceil_div](candidates/425c201df6ac0c0002bca7c2ba6ced5a05f6b2b2e60589fefca9b5be70ae1747.txt) | Review issue | `24ea7eea7244e6a854c570db8dc16d795d4b140a7ccbccfd68cabe53ee5778cf` |
| javascript | glm | [javascript-longest_run](candidates/f0206985070dfa8cf9c811444ee8f6490be9bc58c02dd18f8cc657f935be0e84.txt) | Verified | `5e4038d6b6839fc27000f014fea073af5bef75403cc48a64985c00468d9c40e7` |
| json | deepseek | [json-invoice](candidates/40d6c2f6d39227f3a7656ec52fab6899a337587726a709b71998dda31c161b57.txt) | Review issue | `2441e0b3c04178a1c9601da0ccc6a817c190634adcd8f6b127c5a8000b4a7044` |
| json | glm | [json-invoice](candidates/6da65c2e14f06ff253efbbf5febfc97c54349057032ec6dafa03f2400e366d5e.txt) | Review issue | `167de90ef744390806920d465c6f9c74824bafa2558afdaea2d0277f934a113d` |
| json | deepseek | [json-schedule](candidates/4bff9bf1d222124924f60c46f416396e0da00625d213b94c01169a815d984068.txt) | Verified | `fd58cf93b846e6b5d880cb04654700c9cac4a4c1e18d383bca1dd48c95b2cbb6` |
| json | glm | [json-schedule](candidates/74500396908e53c793799eb6955ea06c5ef732706cf8182250a96fa62b80679e.txt) | Review issue | `bd67c067b4e4536aef0a5683b43a479a60009788c22282242558f9e5ca21a773` |
| json | deepseek | [json-temperature](candidates/c9a11eee4ca3bc79718e03a0f68c302c438d1d2f17f4570e0b1379a5cfd32fa7.txt) | Verified | `6b88e2f2c87b71a2cf09d75b28f5db613dbcdbe6ef95aed9006880824e42db90` |
| json | glm | [json-temperature](candidates/63ca4515b7a7174a92bbb7bdba8de6fd22bcc8b3c89a07e3fa575b4b98432b6b.txt) | Review issue | `d72d0cb84efba21ce4c0b589dadf6783548b91ddfc65b7ad32d60f83a280180a` |
| lua | deepseek | [lua-ceil_div](candidates/5409fb9c31edc2e98fd69e794dea0aa255cee103663b3b69395df19aac3d0ce6.txt) | Verified | `17a1b9c27c2ab8d9b99fecb8ba4380e18f5c1752642b43ee2be71fae766d0a1e` |
| lua | glm | [lua-ceil_div](candidates/e4764a99b49bfaf4015b9f3d0386b0320933529c7d71f42a1db60eca6d6ad884.txt) | Review issue | `2e72693b1a30dd82c667ab1afb1ce8463a5697fb9c5d88b09048f6e37ee274bd` |
| lua | deepseek | [lua-longest_run](candidates/3f9b8a6e6a74110183b5bdf4f62cf0c2d14ed5713f5b694524b35ebe56733ba7.txt) | Verified | `e6e1dad5bea262434e2f445a69305d129ae54012a7c6b59c7a5f1614b0c6f3e1` |
| lua | glm | [lua-longest_run](candidates/e9e6122091a5e208ce95f0b1a931a23e2072973a3fb17788682a5959852abf21.txt) | Verified | `51d55a41de996d96ab87cc2fc0ceff7d4f4b9accfae2f098d10bfd6cadf046e1` |
| lua | deepseek | [lua-parse_decimal](candidates/bc6f00b160d1d7cd279816be7af674eb3fd7de3b1f3f9d03f750d4cfc02e3d8d.txt) | Verified | `7924e83715c8b7b553ae72b8085d90b3ec0a837ca7d66d784acf53eb04e57545` |
| lua | glm | [lua-parse_decimal](candidates/0cb1679097e9729683cf37b6f1dbe6d6f812a719227b2a29b75be61098682bf4.txt) | Review issue | `03131adee7f9703fe206549306c55f4d6071b8766b43120a1d779a7e0f705ea3` |
| python | deepseek | [python-ceil_div](candidates/060d916c2278860ae9005b85d43b03f894ae71008ca13a2ded65e453887c07e1.txt) | Verified | `99c0f7293f674a78d7b20c3b6f23b8df3718d545de5b9352425bb3b1070e42e9` |
| python | glm | [python-ceil_div](candidates/339f9cbdd589f62fdb73c9e634238df371fef7c1c1f0bd7bd61a3aae9ca155f0.txt) | Verified | `a741820d04ad674e6a96808da3b711fc57ce4254833cc015a997383453361cc3` |
| python | deepseek | [python-longest_run](candidates/29aabb5504b9931f169c1516884f78c2a31376362b6216439cb269ce932483ab.txt) | Verified | `9c3e982ea3bb63be3f00efaaf4650b3f0eab372a124ad77aa43fd2f5e0e4792a` |
| python | glm | [python-longest_run](candidates/bdaff1ecaa59d3ce1f9d71815e6c69f3c770accbfaa5c07cbc30f81f54ef68c5.txt) | Verified | `c9f2633b8ba6233b7e3b530940219b909fb7975abee39ad8cb319c647b8d1bb6` |
| python | glm | [python-parse_decimal](candidates/a4c2b703a772a388fa1a06d4bbcfc4c516d79f8be9cca98603531abe94278061.txt) | Review issue | `3ff53899f294dadccb822073215b7bfce66f8f650c331a2aacead7c3ab69d9fc` |
| ruby | deepseek | [ruby-ceil_div](candidates/11c7ade3709871c7351c9abc03be7844f405251f91afd6a83c08ea8f9ebc7074.txt) | Verified | `273b972cf87e76e07720ea780c135977faf5180e715dd2a0d0a1120feb95ac40` |
| ruby | glm | [ruby-ceil_div](candidates/a8c7bd8648415c5bc3ff994aed9fbea964cfc0f1aa4edce816486ae476dd6326.txt) | Review issue | `e8a8015dd30bd3e88f8d53b90aa4260d283025ecc2edc0ca820023bc17cc3a8c` |
| ruby | deepseek | [ruby-parse_decimal](candidates/32dca747c2e37d38f04334a12b430735d897c82f955c0e710f24f85c16f17101.txt) | Review issue | `b90d843fdfc9285882b59dbdc9c858499328f37e11f14ae9ba90eb648b2642d7` |
| rust | deepseek | [rust-ceil_div](candidates/decafaee2909ae5b268bd37693e025e7bd62a5cd0c5b78db43ed8c7e248c3b7e.txt) | Verified | `c9943ee3907d48cee885948c5ded223076b6b8f8591b10c10a87073cc47a3876` |
| rust | glm | [rust-ceil_div](candidates/6a9dbf1717390b84a453c9b9e84bd0fbcee06684138cf5e0f204aab206d627d7.txt) | Review issue | `28d7322a9dc2291adfefc54af664983e1b5afe49ced08878bf4ef323011bcefe` |
| rust | deepseek | [rust-longest_run](candidates/58f2587330eadfc1cf97ef8b5d57ec3e424ec49ff4a4d437f7f43eb449eed008.txt) | Verified | `6d7554f17dee5d71d20479747ebb85a3c77ddd6c86e423420f22f0c1a451af00` |
| rust | glm | [rust-longest_run](candidates/8f9f20e16ed239eb80b845e8a3d9966f23b22d8f98503ec465fe7c7429b6e00f.txt) | Verified | `9e7de0926357631397f88b5e1ab52eba9016f36963fff7081dc21dc96e8bf17e` |
| swift | deepseek | [swift-ceil_div](candidates/0b64210f95841ef062474138266b9d1becbd293ec7304f074e3113652e8762ba.txt) | Verified | `ea79c796f28df09a82f1462472304136381984c52edb23c69c6911a98545d13b` |
| swift | glm | [swift-ceil_div](candidates/b803c1f31e0dca9f9f3454bba998f0bc3ea971a39a034e3ae6a89df4fa9dce67.txt) | Review issue | `71e1e0c89b85f010204eb8b15c9b641e3d9fdde58439f8bdf9900b30bb504f34` |
| swift | deepseek | [swift-longest_run](candidates/9a33712699d02e3f901ec0a84d74d71fb3bd00c484247256f33dd33e85741efb.txt) | Verified | `6e7be5fa86a58c49b93b4760323b4cefe8c72154a095815974ebe8993257461c` |
| swift | glm | [swift-longest_run](candidates/69e3fb65aa7d54d7f0b01bf8f7b842efcab5e64bcf3b91a4bfd1cc3a766eb549.txt) | Verified | `4f93b869d54351496fca894b50ea026dd04ddc926cc65984e944d5ce8ff694e1` |
| swift | deepseek | [swift-parse_decimal](candidates/af00d7967f36f7487eb7fe721a65eae8a23b5840ad3ea2f63025391d21b8d35d.txt) | Review issue | `df9f88e3603a41bd4efc3acbd3473fcf015a086b2126d89f0939dfa56b10f0c7` |
| toml | deepseek | [toml-invoice](candidates/d7c4880b8f4686b7d2ba0c5c2f734b1e3f0154133fd72410779c6d43826b2258.txt) | Review issue | `3198db8ab9345048c6cf79d707ed84b637f3d76d05c71bdc6c647a1d0834d071` |
| toml | glm | [toml-invoice](candidates/dd1a0e25209746c6dbaf0415cad6bc9c6ad2e051dd5dea14a7982d91e746470d.txt) | Review issue | `a4c4f43d3af1172438fa3ee36d3b9ad2e529fbd3fcf9b3c0432130b5aeaf946b` |
| toml | deepseek | [toml-schedule](candidates/c3195f81438bf62089fdf3801d2f13043a04dc0b31e40f47058360b6544c1957.txt) | Review issue | `a30ab5c6cd83f543c07ef10bf9ec467fff6d6d0a3b0e0b2af9b0cab8421e162d` |
| toml | glm | [toml-schedule](candidates/d1bbc12432d69797f10cbe6c1b4defb1f5e4779dde481ce6b895330427590aa0.txt) | Review issue | `8b9f93be88a52b65411a6dbfbb73c2ec3901ef29df201d655fca1e799163cb93` |
| toml | deepseek | [toml-temperature](candidates/37903ce55afee4e535a3650b177e22d6f0422df0698ee8102576e9bc28c39fba.txt) | Verified | `54f910a0f135a65745c73deb3520085204f79363bec73992e2ac7fd166e01613` |
| toml | glm | [toml-temperature](candidates/b326cf6bb6f7c0ba9bd95ab72d0c60d9480abe6e8192048c3a4aaf3112df38dc.txt) | Review issue | `e439ff5171c4a01dff9bfe6961fae251df3727da5357630e95a769a9ed34002c` |
| typescript | deepseek | [typescript-ceil_div](candidates/f30c00d9fc01232e3f65773cb7a0218b61593e4f6085444664c8035f0cb0f9e1.txt) | Verified | `7c570282e34435e2013aa6ed7cf2dd999477cfe147955a8c13686c15f48068ba` |
| typescript | glm | [typescript-ceil_div](candidates/2c3d7d6367787444b22667c2af1f5825ae8893b96d5b839e81d1da02536569ae.txt) | Verified | `53b3917187d886ef1178655d356ad2eb06a597b6b91f184e3d06d26702626050` |
| typescript | glm | [typescript-longest_run](candidates/0a3c8c78052ebe80a32e699c39b34fe44343d580e7f1e9dbdf248ea49208a9d7.txt) | Verified | `c165a3b24d6aaaad1d853f044755f7753c76f644fa03f4eb3c2c2b65d06a7e6d` |
| xml | deepseek | [xml-invoice](candidates/ca10df5849de0980f728f51036fb4ed2809b28a9c27983ddc7d341e88c00e041.txt) | Review issue | `9c253a02c51589c4012caf1670824f90634066769f7d3c3b58c9c248c0fd339e` |
| xml | deepseek | [xml-schedule](candidates/8caa3f0db04c664e8d31846e2a90ae908bb44699c84ec3ef7d879c0612e7ec0e.txt) | Verified | `f8254f7a8b06c1cfea8890af5336b304c6776a45a9362b79666c382e13e73cc7` |
| xml | deepseek | [xml-temperature](candidates/4de7289431885a69a07638078d5a96e118a33237072013142539f8b882a33c2a.txt) | Verified | `21fa9373589ecba022cc95c8e163f2d5555406a94be1b36ec64d98ae853a8862` |
| yaml | deepseek | [yaml-invoice](candidates/87b58ea99cdaa12dc49c4bdcf4f18c5929183b45ae67ab690f203bf7a803f70f.txt) | Review issue | `f0da35b0d548dd7af4d048272b5071e6cf15425afb6b688ff0a425aaaa3c83a8` |
| yaml | glm | [yaml-invoice](candidates/aba51b5c6775168d574f7c0d97f95b3f3e885596c0ae3be8f63992a249a396a9.txt) | Review issue | `306e0ebfb11ec5330340f49223464680f3c07d535a862da663dee833be5b21fc` |
| yaml | deepseek | [yaml-schedule](candidates/e09b227200412c2ecd38f20fc99aba493ee31fbf7b5d59f0b529e9ca338ea902.txt) | Verified | `79953e2ed323aa98f97bd8c55092dea4e3c18890a9be88c688d7864df439c38a` |
| yaml | glm | [yaml-schedule](candidates/272b7a56057a3aee6bee4f88ec1293783ce8a71c497d0ec75f8c1982b0ac2072.txt) | Review issue | `8623679805afbfadd569d2044d2168df71eaa749d16e0152ccbbb17d04bc9dcf` |
| yaml | deepseek | [yaml-temperature](candidates/68c29ee6cc2e279cd18f35ac1fcb2f13270fbbb3595e4fcea817bea893409070.txt) | Verified | `064b6920e4cd831470faa0392f3863354e5845ea4bf00f420e1d272516345f51` |
| yaml | glm | [yaml-temperature](candidates/145a2bd97079663b95f9f77c22138039881fe41d80cc09c5665ec3b072477d76.txt) | Review issue | `de3bcf484bd150f4a1804ab4618d4e61e7e66cea73c53cb8e63d4a280b8ae9b4` |
