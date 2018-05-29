Rails.application.routes.draw do
  passwordless_for :users

  root "trophies#index"

  resources :competitions, only: [:create, :new]
  resource :my_profile, only: [:edit, :update], controller: :profile

  get "/trophies/:year", year: /20\d{2}/, to: "trophies#index", as: :trophies_by_year
  resources :trophies
end
