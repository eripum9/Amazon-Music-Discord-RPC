ObjC.import('Foundation');

function jsValue(value) {
  try {
    return ObjC.unwrap(value);
  } catch (error) {
    return value;
  }
}

function textValue(value) {
  if (value === undefined || value === null) return '';
  try {
    return String(jsValue(value));
  } catch (error) {
    return '';
  }
}

function numberValue(value) {
  const number = Number(jsValue(value));
  return Number.isFinite(number) ? number : null;
}

function run() {
  const mediaRemote = $.NSBundle.bundleWithPath(
    '/System/Library/PrivateFrameworks/MediaRemote.framework/'
  );
  if (!mediaRemote || !mediaRemote.load) {
    return JSON.stringify({status: 'framework_unavailable'});
  }

  const request = $.NSClassFromString('MRNowPlayingRequest');
  if (!request) return JSON.stringify({status: 'request_unavailable'});

  const playerPath = request.localNowPlayingPlayerPath;
  const client = playerPath ? playerPath.client : null;
  const bundleIdentifier = client ? textValue(client.bundleIdentifier) : '';
  if (bundleIdentifier !== 'com.amazon.music') {
    return JSON.stringify({
      status: 'not_amazon_music',
      bundle_identifier: bundleIdentifier,
    });
  }

  const item = request.localNowPlayingItem;
  if (!item) {
    return JSON.stringify({
      status: 'no_item',
      bundle_identifier: bundleIdentifier,
    });
  }

  const info = item.nowPlayingInfo;
  const metadata = item.metadata;
  const infoValue = key => info ? info.valueForKey(key) : null;
  const playbackRate = metadata ? numberValue(metadata.playbackRate) : null;

  return JSON.stringify({
    status: 'found',
    bundle_identifier: bundleIdentifier,
    display_name: client ? textValue(client.displayName) : '',
    title: textValue(infoValue('kMRMediaRemoteNowPlayingInfoTitle')),
    artist: textValue(infoValue('kMRMediaRemoteNowPlayingInfoArtist')),
    album: textValue(infoValue('kMRMediaRemoteNowPlayingInfoAlbum')),
    duration: metadata ? numberValue(metadata.duration) : null,
    position: metadata ? numberValue(metadata.calculatedPlaybackPosition) : null,
    playback_rate: playbackRate,
    playback_status: playbackRate !== null && playbackRate > 0 ? 'playing' : 'paused',
    artwork_url: textValue(infoValue('kMRMediaRemoteNowPlayingInfoArtworkIdentifier')),
    artwork_mime_type: metadata ? textValue(metadata.artworkMIMEType) : '',
  });
}
