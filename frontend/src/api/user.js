const BASE_URL = import.meta.env.VITE_API_BASE_URL

const getHeaders = (token) => ({
  Authorization: `Bearer ${token}`,
})

export const getProfileApi = async (token) => {
  const res = await fetch(`${BASE_URL}/user/me`, {
    headers: getHeaders(token),
  })
  return res.json()
}

export const updateProfileApi = async (token, formData) => {
  const res = await fetch(`${BASE_URL}/user/update-profile`, {
    method: 'PUT',
    headers: getHeaders(token),
    body: formData,
  })
  return res.json()
}

export const upgradeRequestApi = async (token) => {
  const res = await fetch(`${BASE_URL}/user/upgrade-plan`, {
    method: 'POST',
    headers: getHeaders(token),
  })
  return res.json()
}
