import unittest

from domain import CopyCard, Offer, HubState, copy_from_dict, copy_to_dict, offer_from_dict, offer_to_dict, state_from_dict, state_to_dict


class CopyCardSerializationTests(unittest.TestCase):
    def test_legacy_copy_defaults_new_artifact_fields_to_none(self) -> None:
        card = copy_from_dict({"id": "copy-1", "title": "Oferta", "text": "Copy"})

        self.assertIsNone(card.transcript_path)
        self.assertIsNone(card.audio_signature)
        self.assertIsNone(card.transcript_signature)
        self.assertIsNone(card.render_signature)

    def test_copy_round_trips_artifact_paths_and_signatures(self) -> None:
        original = CopyCard(
            id="copy-1",
            transcript_path="C:/output/transcricoes/oferta.json",
            audio_signature="audio-signature",
            transcript_signature="transcript-signature",
            render_signature="render-signature",
        )

        restored = copy_from_dict(copy_to_dict(original))

        self.assertEqual(restored.transcript_path, original.transcript_path)
        self.assertEqual(restored.audio_signature, original.audio_signature)
        self.assertEqual(restored.transcript_signature, original.transcript_signature)
        self.assertEqual(restored.render_signature, original.render_signature)

    def test_copy_round_trips_an_individual_headline(self) -> None:
        original = CopyCard(
            id="copy-1",
            headline={"headline_text": "OFERTA\nESPECIAL", "headline_duration": 2.5, "headline_font_size": 54},
        )

        restored = copy_from_dict(copy_to_dict(original))

        self.assertEqual(restored.headline, original.headline)

    def test_copy_card_keeps_the_original_positional_argument_order(self) -> None:
        card = CopyCard(
            "copy-1",
            "Oferta",
            "Texto",
            "manual",
            "voice-1",
            "C:/audio.mp3",
            "audio_ready",
            "C:/output.mp4",
            "C:/subtitle.ass",
            "erro",
        )

        self.assertEqual(card.status, "audio_ready")
        self.assertEqual(card.output_path, "C:/output.mp4")
        self.assertEqual(card.subtitle_path, "C:/subtitle.ass")
        self.assertEqual(card.error, "erro")
        self.assertIsNone(card.transcript_path)

    def test_state_from_dict_loads_a_legacy_state_without_artifact_fields(self) -> None:
        state = state_from_dict(
            {
                "settings": {"output_folder": "C:/output"},
                "copies": [
                    {
                        "id": "copy-1",
                        "title": "Oferta",
                        "text": "Texto",
                        "status": "rendered",
                        "output_path": "C:/output/oferta.mp4",
                    }
                ],
            }
        )

        self.assertEqual(state.settings.output_folder, "C:/output")
        self.assertEqual(state.copies[0].status, "rendered")
        self.assertEqual(state.copies[0].output_path, "C:/output/oferta.mp4")
        self.assertIsNone(state.copies[0].transcript_path)
        self.assertIsNone(state.copies[0].audio_signature)
        self.assertIsNone(state.copies[0].transcript_signature)
        self.assertIsNone(state.copies[0].render_signature)

    def test_legacy_copies_are_migrated_to_a_single_active_offer(self) -> None:
        state = state_from_dict({"settings": {"takes_folder": "C:/takes"}, "copies": [{"id": "copy-1", "title": "Legada"}]})

        self.assertEqual(len(state.offers), 1)
        self.assertEqual(state.active_offer_id, state.offers[0].id)
        self.assertEqual(state.offers[0].takes_folder, "C:/takes")
        self.assertEqual(state.offers[0].copies[0].title, "Legada")

    def test_offer_state_round_trip_keeps_media_and_copies_isolated(self) -> None:
        state = HubState(
            offers=[
                Offer(id="kids", name="Kids", slug="kids", takes_folder="C:/kids/takes", copies=[CopyCard(id="kids-copy")]),
                Offer(id="music", name="Music", slug="music", takes_folder="C:/music/takes", copies=[CopyCard(id="music-copy")]),
            ],
            active_offer_id="music",
        )

        restored = state_from_dict(state_to_dict(state))

        self.assertEqual(restored.active_offer_id, "music")
        self.assertEqual(restored.offers[0].copies[0].id, "kids-copy")
        self.assertEqual(restored.offers[1].takes_folder, "C:/music/takes")
        self.assertEqual(restored.copies[0].id, "music-copy")

    def test_legacy_audio_folder_deserializes_as_api_audio_folder(self) -> None:
        offer = offer_from_dict({"id": "a", "name": "A", "slug": "a", "audio_folder": "C:/old/audios"})

        self.assertEqual(offer.api_audio_folder, "C:/old/audios")

    def test_offer_serialization_keeps_explicit_audio_paths_and_legacy_api_alias(self) -> None:
        offer = Offer(
            id="a",
            name="A",
            slug="a",
            api_audio_folder="C:/a/audios_api",
            manual_audio_inbox_folder="C:/a/audios_manuais/entrada",
            manual_audio_library_folder="C:/a/audios_manuais/biblioteca",
        )

        payload = offer_to_dict(offer)
        restored = offer_from_dict(payload)

        self.assertEqual(payload["audio_folder"], "C:/a/audios_api")
        self.assertEqual(restored.api_audio_folder, "C:/a/audios_api")
        self.assertEqual(restored.manual_audio_inbox_folder, "C:/a/audios_manuais/entrada")
        self.assertEqual(restored.manual_audio_library_folder, "C:/a/audios_manuais/biblioteca")

    def test_offer_and_copy_round_trip_background_music_rules(self) -> None:
        offer = Offer(
            id="kids",
            name="Kids",
            slug="kids",
            background_music_mode="category",
            background_music_category="infantil",
            copies=[
                CopyCard(
                    id="copy-1",
                    background_music_mode="track",
                    background_music_track_path="C:/musicas/infantil/ukulele.mp3",
                )
            ],
        )

        restored = offer_from_dict(offer_to_dict(offer))

        self.assertEqual(restored.background_music_mode, "category")
        self.assertEqual(restored.background_music_category, "infantil")
        self.assertEqual(restored.copies[0].background_music_mode, "track")
        self.assertEqual(restored.copies[0].background_music_track_path, "C:/musicas/infantil/ukulele.mp3")

    def test_legacy_state_uses_music_disabled_defaults(self) -> None:
        state = state_from_dict({"offers": [{"id": "a", "name": "A", "slug": "a", "copies": [{"id": "c"}]}]})

        self.assertEqual(state.settings.background_music_offset_db, -18.0)
        self.assertEqual(state.offers[0].background_music_mode, "none")
        self.assertEqual(state.copies[0].background_music_mode, "inherit")
