Rails.application.routes.draw do
  passwordless_for :users

  root "trophies#index"

  resources :competitions, only: [:create, :new]
  resource :my_profile, only: [:edit, :update], controller: :profile

  get "/trophies/:season", season: /\d{4}-\d{4}/, to: "trophies#index", as: :trophies_by_season
  resources :trophies
end
