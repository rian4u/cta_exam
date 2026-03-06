export async function onRequestGet() {
  return Response.json({
    email: "rian4u@naver.com",
    message:
      "잘못된 문제나 해설, 오탈자, 기능 오류가 있으면 아래 메일로 알려주세요.",
  });
}
