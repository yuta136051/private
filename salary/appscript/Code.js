function doGet() {
  return HtmlService.createHtmlOutputFromFile('index')
    .setTitle('給与ダッシュボード')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}
